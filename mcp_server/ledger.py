"""Cash rules for Campus Customs, in one place.

The MCP request tools (server.py) and the backend approve route both use this
module, so "no negative cash", "a vendor with an open unpaid invoice will not
ship", and "nothing is paid twice" are written once.

`approve_request` is the ONLY code that moves cash. It is deliberately not an
MCP tool: agents can only ask, and only a human click on the board approves.

Requests are stored as one line in tickets.notes (no new table):

    [REQUEST R102-1 | PENDING | 2026-08-31 | by accounting] kind=rent ref=1 amount=2400.00 account=checking :: <plain text>

On approval the status becomes "APPROVED by <name> on <date>"; on decline,
"DECLINED by <name> on <date>". A declined request is never filed again on that ticket.
"""

from __future__ import annotations

import calendar
import os
import re
import shutil
import sqlite3
import time
from datetime import date
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "campus_customs_new.db"
ORIGINAL_DB_PATH = DATA_DIR / "campus_customs.db"
assert DB_PATH.name == "campus_customs_new.db", "never point the tools at the original database"

AGENT_NAMES = {"boss", "inventory", "accounting", "facilities", "customer_service", "customer service"}
REQUEST_RE = re.compile(
    r"^\[REQUEST (?P<id>R\d+-\d+) \| (?P<status>[^|\]]+?) \| (?P<date>[\d-]+) \| by (?P<by>[^\]]+)\] "
    r"(?P<kv>[^:]*?) :: (?P<text>.*)$"
)


# ---------- basics ----------

def connect(write: bool = False) -> sqlite3.Connection:
    """Open the working copy (read-only unless write=True); fails if the file is missing."""
    mode = "rw" if write else "ro"
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode={mode}", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def today(con: sqlite3.Connection) -> date:
    return date.fromisoformat(con.execute("SELECT date_today FROM desk").fetchone()["date_today"])


def refuse(reason: str, **facts) -> dict:
    return {"ok": False, "refused": reason, **facts}


def ticket_notes(con: sqlite3.Connection, ticket_id: int) -> str:
    row = con.execute("SELECT notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    return (row["notes"] or "") if row else ""


def append_ticket_note(con: sqlite3.Connection, ticket_id: int, note: str) -> bool:
    cur = con.execute(
        "UPDATE tickets SET notes = CASE WHEN notes IS NULL OR notes = '' THEN ?"
        " ELSE notes || char(10) || ? END WHERE id = ?",
        (note, note, ticket_id),
    )
    return cur.rowcount == 1


# ---------- the cash rules ----------

def open_invoices(con: sqlite3.Connection, vendor_id: int) -> list[dict]:
    """Rule: a vendor will not ship while it has an open unpaid invoice."""
    now = today(con)
    rows = con.execute(
        "SELECT id, amount, due_date, status, description FROM invoices"
        " WHERE vendor_id = ? AND status != 'paid'", (vendor_id,)
    ).fetchall()
    return [{**dict(r), "overdue": date.fromisoformat(r["due_date"]) < now} for r in rows]


def check_cash(con: sqlite3.Connection, account: str, amount: float) -> tuple[float | None, dict | None]:
    """Rule: no negative balance. Returns (balance, None) if it fits, else (balance, refusal)."""
    row = con.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
    if row is None:
        return None, refuse(f"No cash account {account!r}.")
    balance = row["balance"]
    if amount <= 0:
        return balance, refuse("Amount must be more than zero.")
    if amount > balance + 1e-9:
        return balance, refuse(
            "Cash is short. Payments can never take the balance below zero.",
            account=account, balance=balance, amount=amount, short_by=round(amount - balance, 2),
        )
    return balance, None


# ---------- request records (stored in tickets.notes) ----------

def _parse_line(ticket_id: int, line: str) -> dict | None:
    m = REQUEST_RE.match(line)
    if not m:
        return None
    kv = dict(pair.split("=", 1) for pair in m["kv"].split() if "=" in pair)
    status_text = m["status"].strip()
    req = {
        "request_id": m["id"],
        "ticket_id": ticket_id,
        "status": (
            "pending" if status_text == "PENDING"
            else "approved" if status_text.startswith("APPROVED")
            else "declined" if status_text.startswith("DECLINED")
            else status_text.lower()
        ),
        "status_text": status_text,
        "requested_on": m["date"],
        "requested_by": m["by"].strip(),
        "kind": kv.get("kind"),
        "amount": float(kv["amount"]) if "amount" in kv else None,
        "account": kv.get("account"),
        "summary": m["text"].strip(),
    }
    if req["kind"] == "purchase_order":
        req.update(vendor_id=int(kv["vendor"]), sku=kv.get("sku"), size=kv.get("size"), qty=int(kv["qty"]))
    else:
        req["ref_id"] = int(kv["ref"]) if "ref" in kv else None
    return req


def list_requests(con: sqlite3.Connection, status: str | None = None, ticket_id: int | None = None) -> list[dict]:
    sql, args = "SELECT id, notes FROM tickets", ()
    if ticket_id is not None:
        sql, args = sql + " WHERE id = ?", (ticket_id,)
    out = []
    for row in con.execute(sql + " ORDER BY id", args).fetchall():
        for line in (row["notes"] or "").splitlines():
            req = _parse_line(row["id"], line)
            if req and (status is None or req["status"] == status):
                out.append(req)
    return out


def payee(con: sqlite3.Connection, req: dict) -> str | None:
    """Who a request would pay: the vendor for invoices and purchase orders, the landlord for rent."""
    if req["kind"] == "invoice":
        row = con.execute(
            "SELECT v.name FROM invoices i JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?",
            (req.get("ref_id"),),
        ).fetchone()
    elif req["kind"] == "rent":
        row = con.execute("SELECT landlord AS name FROM leases WHERE id = ?", (req.get("ref_id"),)).fetchone()
    elif req["kind"] == "purchase_order":
        row = con.execute("SELECT name FROM vendors WHERE id = ?", (req.get("vendor_id"),)).fetchone()
    else:
        row = None
    return row["name"] if row else None


def _next_request_id(con: sqlite3.Connection, ticket_id: int) -> str:
    n = sum(1 for _ in list_requests(con, ticket_id=ticket_id)) + 1
    return f"R{ticket_id}-{n}"


def add_payment_request(
    con: sqlite3.Connection, ticket_id: int, kind: str, ref_id: int, amount: float,
    account: str, reason: str, requested_by: str,
) -> dict:
    """Validate and record a pending payment request. Moves no money."""
    if kind == "invoice":
        ref = con.execute("SELECT amount, status FROM invoices WHERE id = ?", (ref_id,)).fetchone()
        if ref is None:
            return refuse(f"No invoice {ref_id}.")
        if ref["status"] == "paid":
            return refuse(f"Invoice {ref_id} is already paid.")
        owed = ref["amount"]
    elif kind == "rent":
        ref = con.execute("SELECT monthly_rent FROM leases WHERE id = ?", (ref_id,)).fetchone()
        if ref is None:
            return refuse(f"No lease {ref_id}.")
        owed = ref["monthly_rent"]
    else:
        return refuse(f"Unknown payment kind {kind!r}.")
    if abs(amount - owed) > 0.005:
        return refuse(f"Amount {amount} does not match the {kind} amount {owed}.", amount_owed=owed)
    if any(r["kind"] == kind and r.get("ref_id") == ref_id for r in list_requests(con, "pending")):
        return refuse(f"A payment request for {kind} {ref_id} is already pending. Do not ask twice.")
    if any(r["kind"] == kind and r.get("ref_id") == ref_id for r in list_requests(con, "declined", ticket_id)):
        return refuse(f"A person declined paying {kind} {ref_id} on ticket {ticket_id}. Do not file it again.")
    balance, refusal = check_cash(con, account, amount)
    if refusal:
        return refusal
    if not con.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone():
        return refuse(f"No ticket {ticket_id}.")
    req_id = _next_request_id(con, ticket_id)
    note = (
        f"[REQUEST {req_id} | PENDING | {today(con)} | by {_clean(requested_by)}] "
        f"kind={kind} ref={ref_id} amount={amount:.2f} account={account} :: "
        f"Pay {kind} {ref_id}: {amount:.2f} from {account} (balance {balance:.2f}, after "
        f"{balance - amount:.2f}). Needs human approval. Reason: {_clean(reason)}"
    )
    append_ticket_note(con, ticket_id, note)
    return {
        "ok": True, "request_id": req_id, "status": "pending_human_approval", "paid": False,
        "kind": kind, "ref_id": ref_id, "amount": amount, "account": account,
        "balance_now": balance, "balance_after_if_approved": round(balance - amount, 2),
    }


def add_purchase_request(
    con: sqlite3.Connection, ticket_id: int, vendor_id: int, sku: str, size: str, qty: int,
    account: str, reason: str, requested_by: str,
) -> dict:
    """Validate and record a pending purchase order request. Orders and pays nothing."""
    if qty <= 0:
        return refuse("Quantity must be at least 1.")
    vendor = con.execute("SELECT name, specialty, lead_days FROM vendors WHERE id = ?", (vendor_id,)).fetchone()
    if vendor is None:
        return refuse(f"No vendor {vendor_id}.")
    blocked = open_invoices(con, vendor_id)
    if blocked:
        return refuse(
            f"{vendor['name']} has an open unpaid invoice, so they will not ship. "
            "The invoice must be paid (with human approval) first.",
            open_unpaid_invoices=blocked,
        )
    item = con.execute("SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)).fetchone()
    price = con.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
    if item is None or price is None:
        return refuse(f"No inventory or pricing for {sku!r} size {size!r}.")
    if any(
        r["kind"] == "purchase_order" and (r["vendor_id"], r["sku"], r["size"]) == (vendor_id, sku, size)
        for r in list_requests(con, "pending")
    ):
        return refuse(f"A purchase order request for {sku} size {size} from {vendor['name']} is already pending.")
    if any(
        r["kind"] == "purchase_order" and (r["sku"], r["size"]) == (sku, size)
        for r in list_requests(con, "declined", ticket_id)
    ):
        return refuse(f"A person declined a purchase order for {sku} size {size} on ticket {ticket_id}. Do not file it again.")
    cost = round(price["unit_cost"] * qty, 2)
    balance, refusal = check_cash(con, account, cost)
    if refusal:
        return refusal
    if not con.execute("SELECT 1 FROM tickets WHERE id = ?", (ticket_id,)).fetchone():
        return refuse(f"No ticket {ticket_id}.")
    now = today(con)
    ready = date.fromordinal(now.toordinal() + vendor["lead_days"]).isoformat()
    req_id = _next_request_id(con, ticket_id)
    note = (
        f"[REQUEST {req_id} | PENDING | {now} | by {_clean(requested_by)}] "
        f"kind=purchase_order vendor={vendor_id} sku={sku} size={size} qty={qty} amount={cost:.2f} "
        f"account={account} :: {qty} x {sku} size {size} from {vendor['name']}, est. cost {cost:.2f} "
        f"from {account}, ready about {ready}. Needs human approval. Reason: {_clean(reason)}"
    )
    append_ticket_note(con, ticket_id, note)
    return {
        "ok": True, "request_id": req_id, "status": "pending_human_approval", "ordered": False,
        "vendor": vendor["name"], "specialty": vendor["specialty"], "qty": qty,
        "estimated_cost": cost, "cost_basis": "pricing.unit_cost x qty",
        "ready_by_if_approved_today": ready, "balance_now": balance,
    }


# ---------- approval: the only code that moves cash ----------

def _human_name(raw: str, action: str) -> tuple[str, dict | None]:
    name = _clean(raw)[:60]
    if not name:
        return name, refuse(f"{action}_by is required: the name of the person.")
    if name.lower() in AGENT_NAMES:
        return name, refuse(f"Agents cannot {action} requests. A person must.")
    return name, None


def approve_request(request_id: str, approved_by: str) -> dict:
    """Approve one pending request. Called only by the human approve route, never by agents."""
    name, refusal = _human_name(approved_by, "approve")
    if refusal:
        return refusal
    con = connect(write=True)
    try:
        con.execute("BEGIN IMMEDIATE")  # lock, so two clicks cannot both pay
        req = next((r for r in list_requests(con) if r["request_id"] == request_id), None)
        if req is None:
            return refuse(f"No request {request_id}.", code="not_found")
        if req["status"] != "pending":
            return refuse(f"Request {request_id} is not pending ({req['status_text']}). Nothing is paid twice.")
        now = today(con)
        kind, amount, account = req["kind"], req["amount"], req["account"]
        ref_id = req.get("ref_id")
        lease_next_due = None

        if kind == "invoice":
            inv = con.execute("SELECT amount, status FROM invoices WHERE id = ?", (ref_id,)).fetchone()
            if inv is None:
                return refuse(f"Invoice {ref_id} no longer exists.")
            if inv["status"] == "paid":
                return refuse(f"Invoice {ref_id} is already paid. Nothing is paid twice.")
            if abs(inv["amount"] - amount) > 0.005:
                return refuse(f"Invoice {ref_id} is now {inv['amount']}, not {amount}. Ask again.")
        elif kind == "rent":
            lease = con.execute("SELECT monthly_rent, next_due FROM leases WHERE id = ?", (ref_id,)).fetchone()
            if lease is None:
                return refuse(f"Lease {ref_id} no longer exists.")
            if abs(lease["monthly_rent"] - amount) > 0.005:
                return refuse(f"Rent is now {lease['monthly_rent']}, not {amount}. Ask again.")
            lease_next_due = lease["next_due"]
        elif kind == "purchase_order":
            ref_id = req["vendor_id"]
            blocked = open_invoices(con, ref_id)
            if blocked:
                return refuse(
                    "This vendor has an open unpaid invoice, so they will not ship. Pay that first.",
                    open_unpaid_invoices=blocked,
                )
        else:
            return refuse(f"Unknown request kind {kind!r}.")

        balance, refusal = check_cash(con, account, amount)
        if refusal:
            return refusal
        new_balance = round(balance - amount, 2)

        con.execute(
            "UPDATE cash_accounts SET balance = ?, date = ? WHERE name = ?",
            (new_balance, now.isoformat(), account),
        )
        cur = con.execute(
            "INSERT INTO payments (kind, ref_id, amount, account, paid_at, approved_by)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (kind, ref_id, amount, account, now.isoformat(), name),
        )
        payment_id = cur.lastrowid
        changed = {}
        if kind == "invoice":
            con.execute("UPDATE invoices SET status = 'paid' WHERE id = ?", (ref_id,))
            changed["invoice"] = {"id": ref_id, "status": "paid"}
        elif kind == "rent":
            next_due = _add_month(date.fromisoformat(lease_next_due)).isoformat()
            con.execute("UPDATE leases SET next_due = ? WHERE id = ?", (next_due, ref_id))
            changed["lease"] = {"id": ref_id, "paid_due": lease_next_due, "next_due": next_due}
        # A purchase order pays the vendor; no stock is added until goods really arrive.

        _set_request_status(con, req["ticket_id"], request_id, f"APPROVED by {name} on {now}")
        ticket_status = resolve_ticket_if_done(con, req["ticket_id"])
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return {
        "ok": True, "request_id": request_id, "kind": kind, "amount": amount, "account": account,
        "payment_id": payment_id, "approved_by": name, "paid_at": now.isoformat(),
        "balance_before": balance, "balance_after": new_balance, "changed": changed,
        "ticket_id": req["ticket_id"], "ticket_status": ticket_status,
    }


def decline_request(request_id: str, declined_by: str, reason: str = "") -> dict:
    """Decline one pending request. Moves no cash; only the request's status line changes.
    Called only by the human decline route, never by agents. Not an MCP tool."""
    name, refusal = _human_name(declined_by, "decline")
    if refusal:
        return refusal
    con = connect(write=True)
    try:
        con.execute("BEGIN IMMEDIATE")
        req = next((r for r in list_requests(con) if r["request_id"] == request_id), None)
        if req is None:
            return refuse(f"No request {request_id}.", code="not_found")
        if req["status"] != "pending":
            return refuse(f"Request {request_id} is not pending ({req['status_text']}).")
        now = today(con)
        why = _clean(reason)[:120]
        status = f"DECLINED by {name} on {now}" + (f" ({why})" if why else "")
        _set_request_status(con, req["ticket_id"], request_id, status)
        ticket_status = resolve_ticket_if_done(con, req["ticket_id"])
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()
    return {
        "ok": True, "request_id": request_id, "kind": req["kind"], "amount": req["amount"],
        "declined_by": name, "declined_on": now.isoformat(), "cash_moved": False,
        "ticket_id": req["ticket_id"], "ticket_status": ticket_status,
    }


def _set_request_status(con: sqlite3.Connection, ticket_id: int, request_id: str, status: str) -> None:
    lines = ticket_notes(con, ticket_id).splitlines()
    prefix = f"[REQUEST {request_id} | PENDING |"
    lines = [
        line.replace(prefix, f"[REQUEST {request_id} | {status} |", 1) if line.startswith(prefix) else line
        for line in lines
    ]
    con.execute("UPDATE tickets SET notes = ? WHERE id = ?", ("\n".join(lines), ticket_id))


# ---------- tickets, balance, reset ----------

def open_reasons(con: sqlite3.Connection, ticket_id: int) -> list[str]:
    """Why a ticket cannot be resolved yet. Empty list means it can be resolved.

    Rules:
    - the Boss has recorded a decision on it;
    - no payment or purchase request on it is still pending;
    - a customer order that is short on stock needs a restock purchase order for
      that SKU and size that a person approved or declined (paying a vendor's
      invoice is not enough). Declined requests never hold a ticket open.
    """
    row = con.execute(
        "SELECT type, sku, size, qty, notes FROM tickets WHERE id = ?", (ticket_id,)
    ).fetchone()
    if row is None:
        return ["no such ticket"]
    reasons = []
    if "[DECISION |" not in (row["notes"] or ""):
        reasons.append("no Boss decision yet")
    pending = list_requests(con, "pending", ticket_id)
    if pending:
        reasons.append("waiting for approval: " + ", ".join(r["request_id"] for r in pending))
    if row["type"] == "customer_order" and row["sku"] and row["size"] and row["qty"]:
        stock = con.execute(
            "SELECT qty FROM inventory WHERE sku = ? AND size = ?", (row["sku"], row["size"])
        ).fetchone()
        on_hand = stock["qty"] if stock else 0
        # Settled once a person approved OR declined a restock order for this SKU and size.
        restocked = any(
            r["kind"] == "purchase_order" and r["status"] in ("approved", "declined")
            and (r["sku"], r["size"]) == (row["sku"], row["size"])
            for r in list_requests(con, None, ticket_id)
        )
        if on_hand < row["qty"] and not restocked:
            reasons.append(
                f"short on stock ({on_hand} of {row['qty']} {row['sku']} {row['size']}): "
                "needs a restock purchase order approved or declined by a person"
            )
    return reasons


def resolve_ticket_if_done(con: sqlite3.Connection, ticket_id: int) -> str:
    """Set tickets.status = 'resolved' once open_reasons() is empty. Returns the status."""
    row = con.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if row is None:
        return "missing"
    if row["status"] == "resolved":
        return "resolved"
    if not open_reasons(con, ticket_id):
        con.execute("UPDATE tickets SET status = 'resolved' WHERE id = ?", (ticket_id,))
        return "resolved"
    return row["status"]


def finish_run(ticket_id: int) -> str:
    """Called after an agent run: resolve the ticket if the rule above is met."""
    con = connect(write=True)
    try:
        status = resolve_ticket_if_done(con, ticket_id)
        con.commit()
        return status
    finally:
        con.close()


DECISION_RE = re.compile(r"^\[DECISION \| (?P<date>[\d-]+) \| by [^\]]+\] (?:\[(?P<status>[a-z_]+)\] )?(?P<text>.*)$")


def last_decision(notes: str, requester: str | None = None, ticket_type: str | None = None) -> dict | None:
    """The Boss's most recent decision on a ticket, from its board notes (or None)."""
    found = None
    for line in (notes or "").splitlines():
        m = DECISION_RE.match(line)
        if m:
            found = m
    if not found:
        return None
    text = found["text"].strip()
    if requester and ticket_type == "customer_order":  # never show a customer's name
        text = re.sub(re.escape(requester), "the customer", text, flags=re.IGNORECASE)
    return {"date": found["date"], "status": found["status"], "text": text}


def list_tickets() -> list[dict]:
    con = connect()
    try:
        rows = con.execute(
            "SELECT id, type, requester, subject, sku, size, qty, status, notes FROM tickets ORDER BY id"
        ).fetchall()
        out = []
        for r in rows:
            notes = r["notes"] or ""
            out.append({
                "id": r["id"], "type": r["type"], "subject": r["subject"],
                "sku": r["sku"], "size": r["size"], "qty": r["qty"], "status": r["status"],
                "has_decision": "[DECISION |" in notes,
                "pending_requests": len(list_requests(con, "pending", r["id"])),
                "open_because": [] if r["status"] == "resolved" else open_reasons(con, r["id"]),
                "last_decision": last_decision(notes, r["requester"], r["type"]),
            })
        return out
    finally:
        con.close()


def ticket_status(ticket_id: int) -> str | None:
    con = connect()
    try:
        row = con.execute("SELECT status FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return row["status"] if row else None
    finally:
        con.close()


def get_balance(account: str) -> dict | None:
    con = connect()
    try:
        row = con.execute("SELECT name, balance, date FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        return dict(row) if row else None
    finally:
        con.close()


def ensure_working_copy() -> bool:
    """Create the working copy from the original if it does not exist yet (fresh clone).
    Never overwrites an existing working copy. Returns True if it was created."""
    if DB_PATH.exists():
        return False
    if not ORIGINAL_DB_PATH.exists():
        raise FileNotFoundError(
            f"Missing {ORIGINAL_DB_PATH}. Put the course's campus_customs.db in the data/ folder."
        )
    reset_working_copy()
    return True


def reset_working_copy() -> str:
    """Copy the original over the working copy. Never writes to the original."""
    tmp = DB_PATH.with_suffix(".db.tmp")
    shutil.copyfile(ORIGINAL_DB_PATH, tmp)
    for attempt in range(8):
        try:
            os.replace(tmp, DB_PATH)
            break
        except PermissionError:
            if attempt == 7:
                raise
            time.sleep(0.25 * (attempt + 1))
    return DB_PATH.name


# ---------- helpers ----------

def _clean(text: str) -> str:
    """One line, no characters that would break the request format."""
    return re.sub(r"[\r\n\[\]|]+", " ", str(text)).replace("::", ":").strip()


def _add_month(d: date) -> date:
    year, month = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return d.replace(year=year, month=month, day=min(d.day, calendar.monthrange(year, month)[1]))
