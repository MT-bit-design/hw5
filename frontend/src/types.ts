// Types for the backend's real responses (backend/main.py + mcp_server/ledger.py).

export type AgentName = "boss" | "inventory" | "accounting" | "facilities" | "customer_service";

/** GET /api/tickets -> tickets[] (ledger.list_tickets) */
export interface Ticket {
  id: number;
  type: string; // "customer_order" | "rent_notice" | "price_override"
  subject: string;
  sku: string | null;
  size: string | null;
  qty: number | null;
  status: "open" | "resolved" | string;
  has_decision: boolean;
  pending_requests: number;
  open_because: string[];
  /** The Boss's most recent recorded decision on this ticket (from any run), or null. */
  last_decision: { date: string; status: string | null; text: string } | null;
}

/** The Boss's structured answer (backend/models.py AgentReply). */
export interface AgentReply {
  status: "done" | "needs_human" | "blocked" | "refused";
  answer: string;
  facts: string[];
  human_action: string | null;
}

/** RunState.snapshot()["last_run"] */
export interface LastRun {
  run_id: string;
  ticket: number;
  started_at: string;
  outcome: "running" | "finished" | "error";
  reply?: AgentReply;
  error?: string;
  ticket_status?: string;
  ticket_status_error?: string;
  finished_at?: string;
}

/** Included in /api/tickets and /api/events, so the board knows when a run is done. */
export interface RunSnapshot {
  running: boolean;
  last_run: LastRun | null;
}

export interface TicketsResponse {
  tickets: Ticket[];
  run: RunSnapshot;
}

/** POST /api/tickets/{id}/run (202) */
export interface RunStarted {
  ok: true;
  started: true;
  run_id: string;
  ticket: number;
  events: string;
}

export type EventType = "model_call" | "tool_call" | "handoff" | "answer" | "limit_stop" | "error";

/** GET /api/events -> events[] (main._event_view). Fields depend on `type`. */
export interface AgentEvent {
  time: string;
  run_id: string;
  ticket: number;
  step: number;
  agent: AgentName;
  depth: number;
  type: EventType;
  // tool_call
  tool?: string;
  tool_input?: Record<string, unknown>;
  result?: string;
  // handoff
  from?: AgentName;
  to?: AgentName;
  // model_call / answer / limit_stop / error / handoff (the task text)
  said?: string;
  model?: string;
  served_model?: string;
  tokens?: Record<string, number>;
}

export interface EventsResponse {
  run_id: string | null;
  count: number;
  run: RunSnapshot;
  events: AgentEvent[]; // newest first
}

/** GET /api/requests -> requests[] (ledger.list_requests + payee) */
export interface PayRequest {
  request_id: string;
  ticket_id: number;
  status: "pending" | "approved" | "declined" | string;
  status_text: string;
  requested_on: string;
  requested_by: string;
  kind: "invoice" | "rent" | "purchase_order" | string;
  amount: number | null;
  account: string | null;
  summary: string;
  payee: string | null;
  ref_id?: number | null; // invoice / rent
  vendor_id?: number; // purchase_order
  sku?: string;
  size?: string;
  qty?: number;
}

export interface RequestsResponse {
  status: string;
  count: number;
  requests: PayRequest[];
}

/** POST /api/requests/{id}/approve */
export interface ApproveResponse {
  ok: true;
  request_id: string;
  kind: string;
  amount: number;
  account: string;
  payment_id: number;
  approved_by: string;
  paid_at: string;
  balance_before: number;
  balance_after: number;
  changed: Record<string, unknown>;
  ticket_id: number;
  ticket_status: string;
}

/** POST /api/requests/{id}/decline */
export interface DeclineResponse {
  ok: true;
  request_id: string;
  kind: string;
  amount: number | null;
  declined_by: string;
  declined_on: string;
  cash_moved: false;
  ticket_id: number;
  ticket_status: string;
}

/** GET /api/cash */
export interface CashResponse {
  account: string;
  balance: number;
  as_of: string;
}

/** POST /api/reset */
export interface ResetResponse {
  ok: true;
  reset: string;
  from: string;
  audit_trail: "kept";
  cash: { name: string; balance: number; date: string } | null;
}

/** Any refusal (409 / 404 / 503): {"ok": false, "refused": "..."} */
export interface Refusal {
  ok: false;
  refused: string;
  code?: string;
  [extra: string]: unknown;
}
