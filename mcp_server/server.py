"""Campus Customs MCP server: the only way agents get shop facts.

Every tool opens data/campus_customs_new.db on each call, so answers always
reflect the current working copy and nothing is hardcoded. Most tools are
read-only. The few "board" tools only append notes to a ticket (drafts,
requests, decisions). No tool moves money: payments need a human.
"""

import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "campus_customs_new.db"
assert DB_PATH.name == "campus_customs_new.db", "never point the server at the original database"

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]\d{4}(?!\d)")

mcp = FastMCP("campus-customs")


def _connect(write: bool = False) -> sqlite3.Connection:
    """Open the working copy (read-only unless write=True); fails if the file is missing."""
    mode = "rw" if write else "ro"
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode={mode}", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _today(con: sqlite3.Connection) -> date:
    return date.fromisoformat(con.execute("SELECT date_today FROM desk").fetchone()["date_today"])


def _refuse(reason: str, **facts) -> dict:
    return {"ok": False, "refused": reason, **facts}


def _open_invoices(con: sqlite3.Connection, vendor_id: int) -> list[dict]:
    today = _today(con)
    rows = con.execute(
        "SELECT id, amount, due_date, status, description FROM invoices"
        " WHERE vendor_id = ? AND status != 'paid'", (vendor_id,)
    ).fetchall()
    return [
        {**dict(r), "overdue": date.fromisoformat(r["due_date"]) < today} for r in rows
    ]


def _ticket_notes(con: sqlite3.Connection, ticket_id: int) -> str:
    row = con.execute("SELECT notes FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    return (row["notes"] or "") if row else ""


def _append_ticket_note(con: sqlite3.Connection, ticket_id: int, note: str) -> bool:
    cur = con.execute(
        "UPDATE tickets SET notes = CASE WHEN notes IS NULL OR notes = '' THEN ?"
        " ELSE notes || char(10) || ? END WHERE id = ?",
        (note, note, ticket_id),
    )
    return cur.rowcount == 1


def check_stock(sku: str, size: str) -> dict:
    """Stock on hand and price for one SKU and size, plus the other sizes of that SKU.

    Reads: inventory, pricing.
    """
    with _connect() as con:
        rows = con.execute(
            "SELECT sku, name, size, qty, location FROM inventory WHERE sku = ?", (sku,)
        ).fetchall()
        if not rows:
            return {"found": False, "error": f"No inventory rows for sku {sku!r}."}
        price = con.execute(
            "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()

    match = next((r for r in rows if r["size"] == size), None)
    return {
        "found": match is not None,
        "sku": sku,
        "name": rows[0]["name"],
        "size": size,
        "qty_on_hand": match["qty"] if match else None,
        "in_stock": bool(match and match["qty"] > 0),
        "location": match["location"] if match else None,
        "list_price": price["list_price"] if price else None,
        "unit_cost": price["unit_cost"] if price else None,
        "other_sizes": {r["size"]: r["qty"] for r in rows if r["size"] != size},
    }


def get_bills_and_cash() -> dict:
    """Upcoming rent, unpaid vendor invoices, and cash on hand, dated against desk.date_today.

    Reads: desk, leases, invoices, vendors, cash_accounts.
    """
    with _connect() as con:
        today = _today(con)
        leases = con.execute(
            "SELECT id, space_name, landlord, monthly_rent, next_due FROM leases"
        ).fetchall()
        invoices = con.execute(
            """SELECT i.id, i.vendor_id, v.name AS vendor, i.amount, i.due_date,
                      i.status, i.description
               FROM invoices i LEFT JOIN vendors v ON v.id = i.vendor_id
               WHERE i.status != 'paid'"""
        ).fetchall()
        accounts = con.execute("SELECT name, balance, date FROM cash_accounts").fetchall()

    def days_until(due: str) -> int:
        return (date.fromisoformat(due) - today).days

    lease_list = [
        {**dict(r), "days_until_due": days_until(r["next_due"])} for r in leases
    ]
    invoice_list = [
        {**dict(r), "days_until_due": days_until(r["due_date"]),
         "overdue": days_until(r["due_date"]) < 0}
        for r in invoices
    ]
    total_cash = sum(a["balance"] for a in accounts)
    total_due = sum(r["monthly_rent"] for r in leases) + sum(r["amount"] for r in invoices)
    return {
        "date_today": today.isoformat(),
        "leases": lease_list,
        "unpaid_invoices": invoice_list,
        "cash_accounts": [dict(a) for a in accounts],
        "total_cash": total_cash,
        "total_due": total_due,
        "cash_after_paying_all": total_cash - total_due,
    }


def quote_bulk_order(sku: str, size: str, qty: int) -> dict:
    """Can a bulk order be filled, and what is the lowest unit price that still covers cost?

    Reads: desk, inventory, pricing, vendors.
    """
    with _connect() as con:
        today = _today(con)
        item = con.execute(
            "SELECT name, qty FROM inventory WHERE sku = ? AND size = ?", (sku, size)
        ).fetchone()
        price = con.execute(
            "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()
        vendors = con.execute(
            "SELECT id, name, specialty, lead_days FROM vendors ORDER BY lead_days"
        ).fetchall()

    if item is None or price is None:
        return {"found": False, "error": f"No inventory or pricing for {sku!r} size {size!r}."}

    on_hand = item["qty"]
    list_price, unit_cost = price["list_price"], price["unit_cost"]
    return {
        "found": True,
        "date_today": today.isoformat(),
        "sku": sku,
        "name": item["name"],
        "size": size,
        "qty_requested": qty,
        "qty_on_hand": on_hand,
        "shortfall": max(qty - on_hand, 0),
        "list_price": list_price,
        "unit_cost": unit_cost,
        "list_total": list_price * qty,
        "cost_total": unit_cost * qty,
        "max_discount_pct_before_loss": round((1 - unit_cost / list_price) * 100, 1),
        "vendors": [dict(v) for v in vendors],
    }


# ---------- Tickets ----------

def list_open_tickets() -> dict:
    """All open tickets with their type, subject, and links, plus today's shop date.

    Reads: desk, tickets.
    """
    with _connect() as con:
        today = _today(con)
        rows = con.execute(
            "SELECT id, type, subject, sku, size, qty, lease_id, invoice_id, status, created_at"
            " FROM tickets WHERE status = 'open' ORDER BY id"
        ).fetchall()
    return {"date_today": today.isoformat(), "open_tickets": [dict(r) for r in rows]}


def get_ticket(ticket_id: int) -> dict:
    """One ticket with every field, including notes and any drafts or requests already on it.

    Reads: desk, tickets.
    """
    with _connect() as con:
        today = _today(con)
        row = con.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if row is None:
        return {"found": False, "error": f"No ticket {ticket_id}."}
    return {"found": True, "date_today": today.isoformat(), **dict(row)}


# ---------- Vendors, invoices, leases ----------

def find_restock_vendors(sku: str) -> dict:
    """Which vendors could restock a SKU, their lead time and ready-by date, and whether
    an open unpaid invoice blocks them from shipping.

    Reads: desk, inventory, vendors, invoices.
    """
    with _connect() as con:
        today = _today(con)
        item = con.execute("SELECT name FROM inventory WHERE sku = ? LIMIT 1", (sku,)).fetchone()
        if item is None:
            return {"found": False, "error": f"No inventory rows for sku {sku!r}."}
        vendors = con.execute(
            "SELECT id, name, specialty, lead_days FROM vendors ORDER BY lead_days"
        ).fetchall()
        result = []
        for v in vendors:
            open_inv = _open_invoices(con, v["id"])
            past_for_sku = con.execute(
                "SELECT id, status, description FROM invoices"
                " WHERE vendor_id = ? AND description LIKE ?", (v["id"], f"%{sku}%")
            ).fetchall()
            result.append({
                **dict(v),
                "ready_by_if_ordered_today": (today + timedelta(days=v["lead_days"])).isoformat(),
                "open_unpaid_invoices": open_inv,
                "blocked_by_unpaid_invoice": bool(open_inv),
                "past_invoices_for_this_sku": [dict(p) for p in past_for_sku],
            })
    # Vendors that have invoiced this exact SKU before come first.
    result.sort(key=lambda v: (not v["past_invoices_for_this_sku"], v["lead_days"]))
    return {
        "found": True,
        "date_today": today.isoformat(),
        "sku": sku,
        "name": item["name"],
        "vendors": result,
        "rule": "A vendor will not ship while it has an open unpaid invoice.",
    }


def get_invoice(invoice_id: int) -> dict:
    """One vendor invoice with the vendor, days overdue, and the tickets that point to it.

    Reads: desk, invoices, vendors, tickets.
    """
    with _connect() as con:
        today = _today(con)
        row = con.execute(
            "SELECT i.*, v.name AS vendor, v.specialty, v.lead_days FROM invoices i"
            " LEFT JOIN vendors v ON v.id = i.vendor_id WHERE i.id = ?", (invoice_id,)
        ).fetchone()
        if row is None:
            return {"found": False, "error": f"No invoice {invoice_id}."}
        tickets = con.execute(
            "SELECT id, type, subject, status FROM tickets WHERE invoice_id = ?", (invoice_id,)
        ).fetchall()
    days = (date.fromisoformat(row["due_date"]) - today).days
    return {
        "found": True,
        "date_today": today.isoformat(),
        **dict(row),
        "days_until_due": days,
        "overdue": days < 0 and row["status"] != "paid",
        "linked_tickets": [dict(t) for t in tickets],
    }


def get_lease(lease_id: int) -> dict:
    """One lease with rent, next due date, days until due, and the tickets that point to it.

    Reads: desk, leases, tickets.
    """
    with _connect() as con:
        today = _today(con)
        row = con.execute("SELECT * FROM leases WHERE id = ?", (lease_id,)).fetchone()
        if row is None:
            return {"found": False, "error": f"No lease {lease_id}."}
        tickets = con.execute(
            "SELECT id, type, subject, status, notes FROM tickets WHERE lease_id = ?", (lease_id,)
        ).fetchall()
    days = (date.fromisoformat(row["next_due"]) - today).days
    return {
        "found": True,
        "date_today": today.isoformat(),
        **dict(row),
        "days_until_due": days,
        "overdue": days < 0,
        "linked_tickets": [dict(t) for t in tickets],
    }


# ---------- Pricing ----------

def check_margin(sku: str, unit_price: float, qty: int) -> dict:
    """Margin for selling qty units of a SKU at a proposed unit price.

    Reads: pricing.
    """
    with _connect() as con:
        price = con.execute(
            "SELECT unit_cost, list_price FROM pricing WHERE sku = ?", (sku,)
        ).fetchone()
    if price is None:
        return {"found": False, "error": f"No pricing for sku {sku!r}."}
    cost, lst = price["unit_cost"], price["list_price"]
    return {
        "found": True,
        "sku": sku,
        "qty": qty,
        "unit_price": unit_price,
        "list_price": lst,
        "unit_cost": cost,
        "discount_pct_off_list": round((1 - unit_price / lst) * 100, 1),
        "margin_per_unit": round(unit_price - cost, 2),
        "margin_pct": round((unit_price - cost) / unit_price * 100, 1) if unit_price else None,
        "revenue_total": round(unit_price * qty, 2),
        "cost_total": round(cost * qty, 2),
        "margin_total": round((unit_price - cost) * qty, 2),
        "below_cost": unit_price < cost,
    }


# ---------- Board: drafts, requests, decisions (append a note to the ticket only) ----------

def draft_customer_message(ticket_id: int, message: str, written_by: str) -> dict:
    """Save a draft reply to the customer on the ticket. It is NOT sent to anyone.

    Writes: tickets.notes (append only).
    """
    message = message.strip()
    if not message:
        return _refuse("Draft is empty.")
    if len(message) > 1200:
        return _refuse("Draft is too long (max 1200 characters).")
    if EMAIL_RE.search(message) or PHONE_RE.search(message):
        return _refuse("Drafts must not contain email addresses or phone numbers.")
    con = _connect(write=True)
    try:
        today = _today(con)
        note = f"[DRAFT REPLY - NOT SENT | {today} | by {written_by}] {message}"
        if not _append_ticket_note(con, ticket_id, note):
            return _refuse(f"No ticket {ticket_id}.")
        con.commit()
    finally:
        con.close()
    return {"ok": True, "ticket_id": ticket_id, "saved_as": "draft on the ticket", "sent": False}


def request_payment(
    ticket_id: int,
    kind: Literal["invoice", "rent"],
    ref_id: int,
    amount: float,
    account: str,
    reason: str,
    requested_by: str,
) -> dict:
    """Ask a human to approve paying an invoice or rent. This never pays anything.

    Refuses if the invoice or lease does not exist, the amount does not match,
    the invoice is already paid, or the account does not have enough cash.
    Reads: desk, invoices, leases, cash_accounts, payments. Writes: tickets.notes (append only).
    """
    con = _connect(write=True)
    try:
        today = _today(con)
        if kind == "invoice":
            ref = con.execute("SELECT amount, status FROM invoices WHERE id = ?", (ref_id,)).fetchone()
            if ref is None:
                return _refuse(f"No invoice {ref_id}.")
            if ref["status"] == "paid":
                return _refuse(f"Invoice {ref_id} is already paid.")
            owed = ref["amount"]
        else:
            ref = con.execute("SELECT monthly_rent FROM leases WHERE id = ?", (ref_id,)).fetchone()
            if ref is None:
                return _refuse(f"No lease {ref_id}.")
            owed = ref["monthly_rent"]
        if abs(amount - owed) > 0.005:
            return _refuse(f"Amount {amount} does not match the {kind} amount {owed}.", amount_owed=owed)
        already = con.execute(
            "SELECT COUNT(*) FROM payments WHERE kind = ? AND ref_id = ?", (kind, ref_id)
        ).fetchone()[0]
        if f"Pay {kind} {ref_id}:" in _ticket_notes(con, ticket_id):
            return _refuse(
                f"A payment request for {kind} {ref_id} is already on ticket {ticket_id}, "
                "waiting for a human. Do not ask twice."
            )
        acct = con.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        if acct is None:
            return _refuse(f"No cash account {account!r}.")
        balance = acct["balance"]
        if amount > balance:
            return _refuse(
                "Cash is short. Payments can never take the balance below zero.",
                account=account, balance=balance, amount=amount, short_by=round(amount - balance, 2),
            )
        note = (
            f"[PAYMENT REQUEST - NEEDS HUMAN APPROVAL | {today} | by {requested_by}] "
            f"Pay {kind} {ref_id}: {amount:.2f} from {account} (balance {balance:.2f}, "
            f"after {balance - amount:.2f}). Reason: {reason}"
        )
        if not _append_ticket_note(con, ticket_id, note):
            return _refuse(f"No ticket {ticket_id}.")
        con.commit()
    finally:
        con.close()
    return {
        "ok": True,
        "status": "pending_human_approval",
        "paid": False,
        "kind": kind,
        "ref_id": ref_id,
        "amount": amount,
        "account": account,
        "balance_now": balance,
        "balance_after_if_approved": round(balance - amount, 2),
        "existing_payments_for_this_ref": already,
    }


def request_purchase_order(
    ticket_id: int,
    vendor_id: int,
    sku: str,
    size: str,
    qty: int,
    account: str,
    reason: str,
    requested_by: str,
) -> dict:
    """Ask a human to approve a restock order from a vendor. This never orders or pays.

    Refuses if the vendor has an open unpaid invoice (they will not ship), the SKU/size
    does not exist, or the account cannot cover the cost (pricing.unit_cost x qty).
    Reads: desk, vendors, invoices, inventory, pricing, cash_accounts. Writes: tickets.notes (append only).
    """
    if qty <= 0:
        return _refuse("Quantity must be at least 1.")
    con = _connect(write=True)
    try:
        today = _today(con)
        vendor = con.execute(
            "SELECT name, specialty, lead_days FROM vendors WHERE id = ?", (vendor_id,)
        ).fetchone()
        if vendor is None:
            return _refuse(f"No vendor {vendor_id}.")
        open_inv = _open_invoices(con, vendor_id)
        if open_inv:
            return _refuse(
                f"{vendor['name']} has an open unpaid invoice, so they will not ship. "
                "The invoice must be paid (with human approval) first.",
                open_unpaid_invoices=open_inv,
            )
        item = con.execute(
            "SELECT 1 FROM inventory WHERE sku = ? AND size = ?", (sku, size)
        ).fetchone()
        price = con.execute("SELECT unit_cost FROM pricing WHERE sku = ?", (sku,)).fetchone()
        if item is None or price is None:
            return _refuse(f"No inventory or pricing for {sku!r} size {size!r}.")
        if f"{sku} size {size} from {vendor['name']}" in _ticket_notes(con, ticket_id):
            return _refuse(
                f"A purchase order request for {sku} size {size} from {vendor['name']} is already "
                f"on ticket {ticket_id}, waiting for a human. Do not ask twice."
            )
        cost = round(price["unit_cost"] * qty, 2)
        acct = con.execute("SELECT balance FROM cash_accounts WHERE name = ?", (account,)).fetchone()
        if acct is None:
            return _refuse(f"No cash account {account!r}.")
        if cost > acct["balance"]:
            return _refuse(
                "Cash is short. Payments can never take the balance below zero.",
                estimated_cost=cost, balance=acct["balance"],
            )
        ready = (today + timedelta(days=vendor["lead_days"])).isoformat()
        note = (
            f"[PURCHASE ORDER REQUEST - NEEDS HUMAN APPROVAL | {today} | by {requested_by}] "
            f"{qty} x {sku} size {size} from {vendor['name']} (vendor {vendor_id}), "
            f"est. cost {cost:.2f} from {account}, ready about {ready}. Reason: {reason}"
        )
        if not _append_ticket_note(con, ticket_id, note):
            return _refuse(f"No ticket {ticket_id}.")
        con.commit()
    finally:
        con.close()
    return {
        "ok": True,
        "status": "pending_human_approval",
        "ordered": False,
        "vendor": vendor["name"],
        "specialty": vendor["specialty"],
        "qty": qty,
        "estimated_cost": cost,
        "cost_basis": "pricing.unit_cost x qty",
        "ready_by_if_approved_today": ready,
        "balance_now": acct["balance"],
    }


def record_decision(ticket_id: int, decision: str, decided_by: str) -> dict:
    """Write the final call on a ticket to the board. Does not change money or stock.

    Writes: tickets.notes (append only).
    """
    decision = decision.strip()
    if not decision:
        return _refuse("Decision is empty.")
    con = _connect(write=True)
    try:
        today = _today(con)
        note = f"[DECISION | {today} | by {decided_by}] {decision[:1200]}"
        if not _append_ticket_note(con, ticket_id, note):
            return _refuse(f"No ticket {ticket_id}.")
        con.commit()
    finally:
        con.close()
    return {"ok": True, "ticket_id": ticket_id, "recorded": True}


for _tool in (
    check_stock, get_bills_and_cash, quote_bulk_order,
    list_open_tickets, get_ticket, find_restock_vendors, get_invoice, get_lease, check_margin,
    draft_customer_message, request_payment, request_purchase_order, record_decision,
):
    mcp.tool(_tool)


if __name__ == "__main__":
    mcp.run(show_banner=False)
