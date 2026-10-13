"""Data types shared by the Campus Customs agent team."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from backend.audit import AuditLog

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
StepType = Literal["model_call", "tool_call", "handoff", "answer", "limit_stop", "error"]


class AgentSpec(BaseModel):
    """One role on the team: who it is, its prompt file, and the MCP tools it may call."""

    name: AgentName
    title: str
    prompt_file: str
    mcp_tools: tuple[str, ...]


class AgentReply(BaseModel):
    """What every agent hands back, to the Boss or to whoever delegated the work."""

    status: Literal["done", "needs_human", "blocked", "refused"] = Field(
        description="done = finished; needs_human = a person must approve or act; "
        "blocked = cannot go further; refused = against shop rules."
    )
    answer: str = Field(description="Short plain answer or decision.")
    facts: list[str] = Field(
        default_factory=list, description="Facts from tool results that back the answer, with numbers."
    )
    human_action: str | None = Field(
        default=None, description="What a human must approve or do next, if anything."
    )


class AuditEvent(BaseModel):
    """One row in output/audit_trail.json."""

    time: str
    run_id: str
    ticket: int
    agent: AgentName
    depth: int
    step: int
    step_type: StepType
    tool: str | None = None
    tool_input: dict[str, Any] | None = None
    result_summary: str | None = None
    handoff_from: AgentName | None = None
    handoff_to: AgentName | None = None
    model: str | None = None
    served_model: str | None = None
    tokens: dict[str, int] | None = None


@dataclass
class TicketRun:
    """State shared by every agent working on one ticket."""

    ticket_id: int
    run_id: str
    audit: AuditLog
    steps: int = 0
    redact_names: set[str] = field(default_factory=set)


@dataclass
class TeamDeps:
    """Per-agent run context: who I am, how deep in the delegation chain, and the ticket run."""

    agent: AgentName
    depth: int
    run: TicketRun


class StepLimitReached(RuntimeError):
    """The ticket used up MAX_STEPS_PER_TICKET."""
