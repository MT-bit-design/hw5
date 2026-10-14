"""Builds the five agents and runs the audited agent loop.

- Every agent uses the one model from backend/config.py.
- Shop facts come only from the MCP server (mcp_server/server.py) over stdio.
  Each agent sees just the MCP tools listed in its role file.
- Every agent has a `delegate` tool, so any agent can hand work to any other.
- Every model call, tool call, handoff, and answer is appended to the audit trail.
"""

from __future__ import annotations

import os
import sys
import uuid

from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.mcp import MCPToolset, StdioTransport
from pydantic_ai.messages import RetryPromptPart, ToolCallPart, ToolReturnPart
from pydantic_ai.usage import RunUsage

from backend import config
from backend.agents import SPECS
from backend.audit import AuditLog
from backend.models import AgentName, AgentReply, StepLimitReached, TeamDeps, TicketRun

OUTPUT_TOOL_PREFIX = "final_result"
TICKET_TOOLS = {"get_ticket", "list_open_tickets"}


def build_mcp_toolset() -> MCPToolset:
    """Start mcp_server/server.py over stdio. The API key is not passed to the server."""
    env = {k: v for k, v in os.environ.items() if k != "PORTKEY_API_KEY"}
    transport = StdioTransport(
        command=sys.executable,
        args=[str(config.MCP_SERVER_SCRIPT)],
        cwd=str(config.ROOT),
        env=env,
    )
    return MCPToolset(
        transport, id="campus-customs", max_retries=1, init_timeout=config.MCP_INIT_TIMEOUT_S
    )


def roster(me: AgentName) -> str:
    lines = ["## Your team (use `delegate` to hand work to them)"]
    for spec in SPECS.values():
        if spec.name != me:
            lines.append(f"- `{spec.name}` ({spec.title}): MCP tools {', '.join(spec.mcp_tools)}")
    lines.append(
        f"\nLimits: delegation can go at most {config.MAX_DELEGATION_DEPTH} levels deep, and the whole "
        f"ticket gets at most {config.MAX_STEPS_PER_TICKET} steps. Do not delegate the same question twice."
    )
    return "\n".join(lines)


class Team:
    def __init__(self, audit: AuditLog | None = None):
        self.audit = audit or AuditLog(config.AUDIT_PATH)
        self.mcp = build_mcp_toolset()
        model = config.build_model()
        self.agents: dict[AgentName, Agent[TeamDeps, AgentReply]] = {}
        for spec in SPECS.values():
            allowed = set(spec.mcp_tools)
            prompt = (config.PROMPTS_DIR / spec.prompt_file).read_text(encoding="utf-8")
            self.agents[spec.name] = Agent(
                model,
                name=spec.name,
                deps_type=TeamDeps,
                output_type=AgentReply,
                instructions=prompt + "\n\n" + roster(spec.name),
                toolsets=[self.mcp.filtered(lambda ctx, td, allowed=allowed: td.name in allowed)],
                tools=[self._delegate_tool()],
                model_settings=config.model_settings(),
                retries=1,
            )

    # ---------- delegation ----------

    def _delegate_tool(self):
        team = self

        async def delegate(ctx: RunContext[TeamDeps], to: AgentName, task: str) -> str:
            """Hand a piece of work to another agent and get its answer back.

            Args:
                to: The agent to hand the work to: boss, inventory, accounting, facilities, or customer_service.
                task: A clear, self-contained request with the ticket number and the facts they need.
            """
            me, run = ctx.deps.agent, ctx.deps.run
            if to == me:
                return "Refused: you cannot delegate to yourself. Do the work or pick another agent."
            if ctx.deps.depth + 1 > config.MAX_DELEGATION_DEPTH:
                return (
                    f"Refused: max delegation depth ({config.MAX_DELEGATION_DEPTH}) reached. "
                    "Answer with what you already know and say what is missing."
                )
            team.audit.record(
                run, agent=me, depth=ctx.deps.depth, step_type="handoff", tool="delegate",
                tool_input={"to": to, "task": task}, handoff_from=me, handoff_to=to,
                result_summary=f"{me} handed work to {to}",
            )
            reply = await team.run_agent(to, task, run, depth=ctx.deps.depth + 1, usage=ctx.usage)
            return reply.model_dump_json()

        return delegate

    # ---------- the audited agent loop ----------

    async def run_agent(
        self, name: AgentName, task: str, run: TicketRun, depth: int = 0, usage: RunUsage | None = None
    ) -> AgentReply:
        agent = self.agents[name]
        deps = TeamDeps(agent=name, depth=depth, run=run)
        pending: dict[str, tuple[str, dict]] = {}

        async with agent.iter(
            task, deps=deps, usage=usage, usage_limits=config.USAGE_LIMITS
        ) as agent_run:
            async for node in agent_run:
                if Agent.is_call_tools_node(node):
                    resp = node.model_response
                    calls = [p for p in resp.parts if isinstance(p, ToolCallPart)]
                    for call in calls:
                        pending[call.tool_call_id] = (call.tool_name, call.args_as_dict())
                    self._step(run)
                    self.audit.record(
                        run, agent=name, depth=depth, step_type="model_call",
                        model=config.MODEL_NAME, served_model=resp.model_name,
                        tokens={"input": resp.usage.input_tokens, "output": resp.usage.output_tokens},
                        result_summary="requested tools: "
                        + (", ".join(c.tool_name for c in calls) or "none (text reply)"),
                    )
                elif Agent.is_model_request_node(node):
                    for part in node.request.parts:
                        if isinstance(part, ToolReturnPart | RetryPromptPart) and part.tool_name:
                            self._log_tool_result(run, name, depth, part, pending)
                elif Agent.is_end_node(node):
                    reply = node.data.output
                    self.audit.record(
                        run, agent=name, depth=depth, step_type="answer",
                        model=config.MODEL_NAME,
                        # usage is shared by every agent on the ticket, so this is the ticket total so far
                        tokens={"ticket_input_total": agent_run.usage.input_tokens,
                                "ticket_output_total": agent_run.usage.output_tokens},
                        result_summary=self.audit.summarize(run, reply.model_dump()),
                    )
        return agent_run.result.output

    def _log_tool_result(self, run, name, depth, part, pending) -> None:
        tool_name, args = pending.pop(part.tool_call_id, (part.tool_name, {}))
        if tool_name.startswith(OUTPUT_TOOL_PREFIX):
            return  # the final answer is logged as an "answer" step
        content = part.content
        if isinstance(part, RetryPromptPart):
            content = {"retry": part.model_response()}
        elif tool_name in TICKET_TOOLS:
            self.audit.learn_customer_names(run, content)
        self._step(run)
        self.audit.record(
            run, agent=name, depth=depth, step_type="tool_call", tool=tool_name,
            tool_input=args, result_summary=self.audit.summarize(run, content),
        )

    def _step(self, run: TicketRun) -> None:
        run.steps += 1
        if run.steps > config.MAX_STEPS_PER_TICKET:
            raise StepLimitReached(f"ticket {run.ticket_id} hit {config.MAX_STEPS_PER_TICKET} steps")

    async def _record_decision(self, run: TicketRun, reply: AgentReply) -> None:
        """Put the Boss's final answer on the board through the MCP record_decision tool.
        Done here, not by the Boss mid-turn, so the final answer is one clean step."""
        decision = f"[{reply.status}] {reply.answer}"
        if reply.human_action:
            decision += f" Human action: {reply.human_action}"
        args = {"ticket_id": run.ticket_id, "decision": decision, "decided_by": "boss"}
        result = await self.mcp.direct_call_tool("record_decision", args)
        self.audit.record(
            run, agent="boss", depth=0, step_type="tool_call", tool="record_decision",
            tool_input=args, result_summary=self.audit.summarize(run, result),
        )

    # ---------- entry point ----------

    async def run_ticket(self, ticket_id: int, run_id: str | None = None) -> AgentReply:
        run = TicketRun(ticket_id=ticket_id, run_id=run_id or uuid.uuid4().hex[:12], audit=self.audit)
        task = (
            f"Work ticket {ticket_id}. Read it with get_ticket, including the notes from earlier runs, "
            "send the right parts to the right agents, then give your final call as your answer."
        )
        try:
            async with self.mcp:
                reply = await self.run_agent("boss", task, run)
                await self._record_decision(run, reply)
                return reply
        except (StepLimitReached, UsageLimitExceeded) as exc:
            self.audit.record(
                run, agent="boss", depth=0, step_type="limit_stop", result_summary=str(exc)
            )
            return AgentReply(
                status="blocked", answer=f"Stopped by a safety limit: {exc}",
                human_action="A human should review this ticket.",
            )
        except Exception as exc:
            self.audit.record(
                run, agent="boss", depth=0, step_type="error",
                result_summary=self.audit.summarize(run, f"{type(exc).__name__}: {exc}"),
            )
            raise
