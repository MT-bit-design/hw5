// The one place the board talks to the backend. No keys here, ever.
import type {
  ApproveResponse,
  CashResponse,
  DeclineResponse,
  EventsResponse,
  Refusal,
  RequestsResponse,
  ResetResponse,
  RunStarted,
  TicketsResponse,
} from "./types";

export const API_URL: string = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

/** The backend said no (409/404/503) and explained why in plain words. */
export class RefusedError extends Error {
  readonly status: number;
  readonly body: Refusal;
  constructor(status: number, body: Refusal) {
    super(body.refused);
    this.status = status;
    this.body = body;
  }
}

/** The backend could not be reached at all. */
export class OfflineError extends Error {
  constructor() {
    super(`The backend is not running at ${API_URL}.`);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
    });
  } catch {
    throw new OfflineError();
  }
  const text = await res.text();
  let body: unknown = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    throw new Error(`The backend sent something unexpected (HTTP ${res.status}).`);
  }
  if (!res.ok) {
    if (body && typeof body === "object" && "refused" in body) {
      throw new RefusedError(res.status, body as Refusal);
    }
    const detail = body && typeof body === "object" && "detail" in body ? JSON.stringify((body as { detail: unknown }).detail) : "";
    throw new Error(`The backend returned HTTP ${res.status}. ${detail}`.trim());
  }
  return body as T;
}

const post = (body?: unknown): RequestInit => ({ method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  tickets: () => request<TicketsResponse>("/api/tickets"),
  runTicket: (id: number) => request<RunStarted>(`/api/tickets/${id}/run`, post()),
  events: (params: { ticket?: number; limit?: number; runId?: string }) => {
    const q = new URLSearchParams();
    if (params.ticket !== undefined) q.set("ticket", String(params.ticket));
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    if (params.runId) q.set("run_id", params.runId);
    return request<EventsResponse>(`/api/events?${q}`);
  },
  requests: (status: "pending" | "approved" | "declined" | "all" = "pending") =>
    request<RequestsResponse>(`/api/requests?status=${status}`),
  approve: (id: string, approvedBy: string) =>
    request<ApproveResponse>(`/api/requests/${encodeURIComponent(id)}/approve`, post({ approved_by: approvedBy })),
  decline: (id: string, declinedBy: string, reason: string) =>
    request<DeclineResponse>(`/api/requests/${encodeURIComponent(id)}/decline`, post({ declined_by: declinedBy, reason })),
  cash: () => request<CashResponse>("/api/cash"),
  reset: () => request<ResetResponse>("/api/reset", post()),
};

/** Plain words for any error, for showing on the board. */
export function plainError(err: unknown): string {
  if (err instanceof RefusedError) return err.body.refused;
  if (err instanceof Error) return err.message;
  return "Something went wrong.";
}
