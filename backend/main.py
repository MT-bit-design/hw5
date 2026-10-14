"""Campus Customs backend (FastAPI) for the desk board.

Start it from the backend/ folder:

    uvicorn main:app --reload --port 8000

Paths come from this file's location, so the MCP server, the database, and the
audit trail are found no matter which folder you start from.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from fastapi import FastAPI, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from backend import config  # noqa: E402
from backend.audit import EMAIL_RE, PHONE_RE  # noqa: E402
from backend.team import Team  # noqa: E402
from mcp_server import ledger  # noqa: E402

CASH_ACCOUNT = "checking"

app = FastAPI(title="Campus Customs desk API")
app.add_middleware(
    CORSMiddleware,
    # Only the local React dev server (any localhost port), nothing else.
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# ---------- run state (one agent run at a time) ----------

class RunState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running = False
        self.last: dict[str, Any] | None = None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {"running": self.running, "last_run": dict(self.last) if self.last else None}


RUN = RunState()


def _run_in_thread(team: Team, ticket_id: int, run_id: str) -> None:
    """Agent runs start the MCP server as a subprocess, so they get their own event loop
    (a Proactor loop on Windows, which supports subprocesses)."""
    loop_factory = asyncio.ProactorEventLoop if sys.platform == "win32" else None
    result: dict[str, Any] = {}
    try:
        reply = asyncio.run(team.run_ticket(ticket_id, run_id=run_id), loop_factory=loop_factory)
        result = {"outcome": "finished", "reply": reply.model_dump()}
    except Exception as exc:  # the error is also in the audit trail
        result = {"outcome": "error", "error": _scrub(f"{type(exc).__name__}: {exc}")[:400]}
    finally:
        try:
            result["ticket_status"] = ledger.finish_run(ticket_id)
        except Exception as exc:
            result["ticket_status_error"] = str(exc)
        with RUN.lock:
            RUN.running = False
            RUN.last = {**(RUN.last or {}), **result, "finished_at": _now()}


# ---------- helpers ----------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _refusal(body: dict, default_status: int = 409) -> JSONResponse:
    status = 404 if body.get("code") == "not_found" else default_status
    return JSONResponse(status_code=status, content=body)


def _scrub(value: Any) -> Any:
    """Belt and braces: the audit trail is already scrubbed, but never return a key, email, or phone."""
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if not isinstance(value, str):
        return value
    key = os.getenv("PORTKEY_API_KEY", "").strip()
    if key:
        value = value.replace(key, "[REDACTED-KEY]")
    return PHONE_RE.sub("[REDACTED-PHONE]", EMAIL_RE.sub("[REDACTED-EMAIL]", value))


def _read_audit() -> list[dict]:
    path = config.AUDIT_PATH
    if not path.exists() or not path.stat().st_size:
        return []
    for attempt in range(8):  # the file is replaced atomically; retry if caught mid-replace
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (PermissionError, json.JSONDecodeError):
            if attempt == 7:
                raise
            time.sleep(0.2)
    return []


def _event_view(row: dict) -> dict:
    kind = row.get("step_type")
    view = {
        "time": row.get("time"), "run_id": row.get("run_id"), "ticket": row.get("ticket"),
        "step": row.get("step"), "agent": row.get("agent"), "depth": row.get("depth"), "type": kind,
    }
    if kind == "tool_call":
        view.update(tool=row.get("tool"), tool_input=row.get("tool_input"), result=row.get("result_summary"))
    elif kind == "handoff":
        view.update(**{"from": row.get("handoff_from"), "to": row.get("handoff_to")},
                    said=(row.get("tool_input") or {}).get("task"))
    elif kind == "model_call":
        view.update(said=row.get("result_summary"), model=row.get("model"),
                    served_model=row.get("served_model"), tokens=row.get("tokens"))
    else:  # answer, limit_stop, error
        view.update(said=row.get("result_summary"), tokens=row.get("tokens"))
    return {k: v for k, v in view.items() if v is not None}


# ---------- routes ----------

@app.get("/api/tickets")
def get_tickets() -> dict:
    """The tickets and whether each is open or resolved (tickets.status)."""
    return {"tickets": ledger.list_tickets(), "run": RUN.snapshot()}


@app.post("/api/tickets/{ticket_id}/run", status_code=202)
def run_ticket(ticket_id: int):
    """Start the agent team on one ticket in the background and answer right away."""
    status = ledger.ticket_status(ticket_id)
    if status is None:
        return _refusal({"ok": False, "refused": f"No ticket {ticket_id}.", "code": "not_found"})
    if status == "resolved":
        return _refusal({"ok": False, "refused": f"Ticket {ticket_id} is already resolved."})
    try:
        team = Team()
    except config.MissingApiKey as exc:
        return _refusal({"ok": False, "refused": str(exc)}, default_status=503)
    with RUN.lock:
        if RUN.running:
            return _refusal({
                "ok": False, "refused": "A run is already going. Wait for it to finish.",
                "running_ticket": (RUN.last or {}).get("ticket"),
            })
        run_id = uuid.uuid4().hex[:12]
        RUN.running = True
        RUN.last = {"run_id": run_id, "ticket": ticket_id, "started_at": _now(), "outcome": "running"}
    threading.Thread(target=_run_in_thread, args=(team, ticket_id, run_id), daemon=True).start()
    return {"ok": True, "started": True, "run_id": run_id, "ticket": ticket_id,
            "events": f"/api/events?run_id={run_id}"}


@app.get("/api/events")
def get_events(
    ticket: int | None = Query(None, description="Only this ticket."),
    limit: int = Query(50, ge=1, le=500),
    run_id: str | None = Query(None, description="A specific run. Default: the latest run."),
) -> dict:
    """Recent agent events from the audit trail, newest first. Defaults to the latest run."""
    rows = _read_audit()
    if ticket is not None:
        rows = [r for r in rows if r.get("ticket") == ticket]
    if run_id is None and rows:
        run_id = rows[-1].get("run_id")
    if run_id is not None:
        rows = [r for r in rows if r.get("run_id") == run_id]
    events = [_event_view(r) for r in reversed(rows)][:limit]
    return {"run_id": run_id, "count": len(events), "run": RUN.snapshot(), "events": _scrub(events)}


@app.get("/api/requests")
def get_requests(status: str = Query("pending", pattern="^(pending|approved|all)$")) -> dict:
    """Payment and purchase order requests (pending by default), for the Approve button."""
    con = ledger.connect()
    try:
        reqs = ledger.list_requests(con, None if status == "all" else status)
    finally:
        con.close()
    return {"status": status, "count": len(reqs), "requests": _scrub(reqs)}


class Approval(BaseModel):
    approved_by: str = Field(min_length=1, max_length=60, description="Name of the person approving.")


@app.post("/api/requests/{request_id}/approve")
def approve(request_id: str, body: Approval):
    """Approve one pending request. The only route that moves cash; a human click calls it."""
    if not re.fullmatch(r"R\d+-\d+", request_id):
        return _refusal({"ok": False, "refused": "Bad request id.", "code": "not_found"})
    result = ledger.approve_request(request_id, body.approved_by)
    return result if result.get("ok") else _refusal(result)


@app.get("/api/cash")
def get_cash():
    """The current checking balance from cash_accounts."""
    row = ledger.get_balance(CASH_ACCOUNT)
    if row is None:
        return _refusal({"ok": False, "refused": f"No cash account {CASH_ACCOUNT!r}.", "code": "not_found"})
    return {"account": row["name"], "balance": row["balance"], "as_of": row["date"]}


@app.post("/api/reset")
def reset():
    """Copy the original database over the working copy. Keeps the audit trail."""
    with RUN.lock:
        if RUN.running:
            return _refusal({"ok": False, "refused": "A run is going. Reset after it finishes."})
        name = ledger.reset_working_copy()
    return {"ok": True, "reset": name, "from": ledger.ORIGINAL_DB_PATH.name,
            "audit_trail": "kept", "cash": ledger.get_balance(CASH_ACCOUNT)}
