// Turns audit events into what the desk shows. Pure functions, no model calls.
import type { AgentEvent, AgentName, AgentReply } from "../types";
import { agentTitle, toolLabel } from "./agents";

/** The backend sends answers as a JSON string, sometimes cut at 400 chars. Read it either way. */
export function parseReply(said: string | undefined): Partial<AgentReply> {
  if (!said) return {};
  try {
    const obj = JSON.parse(said);
    if (obj && typeof obj === "object") return obj as AgentReply;
  } catch {
    /* truncated: fall through */
  }
  const field = (key: string): string | undefined => {
    const m = said.match(new RegExp(`"${key}"\\s*:\\s*"((?:[^"\\\\]|\\\\.)*)`));
    if (!m) return undefined;
    let text = m[1];
    if (text.endsWith("...")) text = text.slice(0, -3) + "…";
    try {
      return JSON.parse(`"${text.replace(/\\$/, "")}"`);
    } catch {
      return text;
    }
  };
  const status = field("status") as AgentReply["status"] | undefined;
  return { status, answer: field("answer") ?? said, human_action: field("human_action") ?? null };
}

interface ToolOutcome {
  refused?: string;
  requestId?: string;
}

/** Was a tool call refused, or did it file a request? (result is a JSON summary, maybe cut.) */
export function toolOutcome(result: string | undefined): ToolOutcome {
  if (!result) return {};
  const refused = result.match(/"refused"\s*:\s*"((?:[^"\\]|\\.)*)/);
  const requestId = result.match(/"request_id"\s*:\s*"(R\d+-\d+)"/);
  return { refused: refused?.[1], requestId: requestId?.[1] };
}

export function firstSentence(text: string, max = 180): string {
  const clean = text.replace(/\s+/g, " ").trim();
  const m = clean.match(/^.*?[.!?](\s|$)/);
  const s = (m ? m[0] : clean).trim();
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}

export interface ToolChip {
  key: string;
  tool: string;
  label: string;
  refused?: string;
  requestId?: string;
}

export interface Seat {
  state: "idle" | "active" | "waiting" | "done";
  line: string | null;
  chips: ToolChip[];
  note: { from: AgentName; text: string; key: string } | null;
}

export interface DeskView {
  seats: Record<AgentName, Seat>;
  active: AgentName | null;
}

const AGENT_NAMES: AgentName[] = ["boss", "inventory", "accounting", "facilities", "customer_service"];

function lineFor(e: AgentEvent): string | null {
  switch (e.type) {
    case "model_call": {
      const tools = (e.said ?? "").replace(/^requested tools:\s*/, "").split(",").map((t) => t.trim())
        .filter((t) => t && !t.startsWith("final_result") && t !== "none (text reply)");
      if (!tools.length) return "Putting the answer together…";
      return `Thinking… next: ${tools.map((t) => (t === "delegate" ? "hand off" : toolLabel(t))).join(", ")}`;
    }
    case "tool_call": {
      if (e.tool === "delegate") return null;
      const out = toolOutcome(e.result);
      if (out.refused) return `${capital(toolLabel(e.tool ?? ""))}, but it was refused: ${out.refused}`;
      if (out.requestId) return `${capital(toolLabel(e.tool ?? ""))} (${out.requestId}).`;
      return `${capital(toolLabel(e.tool ?? ""))}.`;
    }
    case "handoff":
      return `Asked ${agentTitle(e.to)}: ${firstSentence(e.said ?? "", 140)}`;
    case "answer": {
      const r = parseReply(e.said);
      return r.answer ? firstSentence(r.answer, 220) : null;
    }
    case "limit_stop":
      return "This run stopped at a safety limit (too many steps or tokens). Nothing was paid.";
    case "error":
      return failureLine(e.said);
  }
}

const capital = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Plain words for a failed run, instead of the raw error text. */
export function failureLine(raw: string | undefined): string {
  const text = raw ?? "";
  const code = text.match(/status_code:\s*(\d{3})/)?.[1];
  let why = "something went wrong";
  if (code) why = `the AI service had an error (HTTP ${code})`;
  else if (/timed out|timeout/i.test(text)) why = "the AI service did not answer in time";
  else if (/connect|session/i.test(text)) why = "the tool server did not start in time";
  return `This run stopped: ${why}. Nothing was paid.`;
}

/** Build the five seats from events (oldest first). */
export function deriveDesk(eventsAsc: AgentEvent[], running: boolean): DeskView {
  const seats = Object.fromEntries(
    AGENT_NAMES.map((n) => [n, { state: "idle", line: null, chips: [], note: null } as Seat]),
  ) as Record<AgentName, Seat>;

  for (const e of eventsAsc) {
    const seat = seats[e.agent];
    if (!seat) continue;
    const line = lineFor(e);
    if (line) seat.line = line;
    if (e.type === "tool_call" && e.tool && e.tool !== "delegate") {
      const out = toolOutcome(e.result);
      seat.chips.push({ key: `${e.run_id}-${e.step}-${e.tool}-${seat.chips.length}`, tool: e.tool, label: toolLabel(e.tool), ...out });
    }
    if (e.type === "handoff" && e.to && seats[e.to]) {
      seats[e.to].note = { from: e.agent, text: firstSentence(e.said ?? "", 160), key: `${e.run_id}-${e.step}-${e.to}` };
      if (seats[e.to].state === "done") seats[e.to].state = "idle";
      seat.state = "waiting";
    }
    if (e.type === "answer") seat.state = "done";
    if (e.type === "error" || e.type === "limit_stop") seats.boss.state = "done";
  }

  let active: AgentName | null = null;
  if (running && eventsAsc.length) {
    const last = eventsAsc[eventsAsc.length - 1];
    active = last.agent;
    if (last.type === "handoff" && last.to) active = last.to;
    if (last.type === "answer" && last.depth > 0) {
      const back = [...eventsAsc].reverse().find((e) => e.type === "handoff" && e.to === last.agent);
      active = back?.from ?? "boss";
    }
  } else if (running) {
    active = "boss";
  }
  if (active) seats[active].state = "active";
  if (!running) {
    for (const n of AGENT_NAMES) if (seats[n].state !== "idle") seats[n].state = "done";
  }
  return { seats, active };
}

export interface AgentSummary {
  agent: AgentName;
  sentence: string;
  tools: { label: string; count: number }[];
  answer: string | null;
}

/** "What each agent did on this ticket", from the events of the shown run. */
export function summarize(eventsAsc: AgentEvent[]): AgentSummary[] {
  const out: AgentSummary[] = [];
  for (const agent of AGENT_NAMES) {
    const mine = eventsAsc.filter((e) => e.agent === agent);
    if (!mine.length) continue;
    const toolCounts = new Map<string, number>();
    const filed: string[] = [];
    const refused: string[] = [];
    for (const e of mine) {
      if (e.type !== "tool_call" || !e.tool || e.tool === "delegate") continue;
      toolCounts.set(toolLabel(e.tool), (toolCounts.get(toolLabel(e.tool)) ?? 0) + 1);
      const o = toolOutcome(e.result);
      if (o.requestId) filed.push(o.requestId);
      if (o.refused) refused.push(o.refused);
    }
    const askedBy = eventsAsc.filter((e) => e.type === "handoff" && e.to === agent).map((e) => agentTitle(e.agent));
    const askedOthers = mine.filter((e) => e.type === "handoff").map((e) => agentTitle(e.to));
    const answers = mine.filter((e) => e.type === "answer");
    const answer = answers.length ? parseReply(answers[answers.length - 1].said).answer ?? null : null;

    const parts: string[] = [];
    if (askedBy.length) parts.push(`asked by ${[...new Set(askedBy)].join(" and ")}`);
    const toolWords = [...toolCounts.entries()].map(([l, c]) => (c > 1 ? `${l} (${c}×)` : l));
    if (toolWords.length) parts.push(toolWords.join(", "));
    if (askedOthers.length) parts.push(`handed work to ${[...new Set(askedOthers)].join(", ")}`);
    if (filed.length) parts.push(`filed ${filed.join(", ")} for your approval`);
    if (refused.length) parts.push(`${refused.length} call${refused.length > 1 ? "s were" : " was"} refused by the shop rules`);
    out.push({
      agent,
      sentence: parts.length ? capital(parts.join("; ")) + "." : "Was on the run but did not act.",
      tools: [...toolCounts.entries()].map(([label, count]) => ({ label, count })),
      answer,
    });
  }
  return out;
}
