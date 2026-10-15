"""Campus Customs MCP server: the only way agents get shop facts.

Every tool opens data/campus_customs_new.db on each call, so answers always
reflect the current working copy and nothing is hardcoded. Most tools are
read-only. The few "board" tools only append notes to a ticket (drafts,
requests, decisions). No tool moves money: payments need a human.

The cash rules live in ledger.py, shared with the backend's approve route.
ledger.approve_request is deliberately NOT registered here, so agents cannot call it.
"""

import re
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Literal

from fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402
from ledger import (  # noqa: E402
    append_ticket_note as _append_ticket_note,
    connect as _connect,
    open_invoices as _open_invoices,
    refuse as _refuse,
    today as _today,
)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]\d{4}(?!\d)")

mcp = FastMCP("campus-customs")


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
    the invoice is already paid, the same request is already pending, or the
    account does not have enough cash. Returns a request_id a human can approve.
    Reads: desk, invoices, leases, cash_accounts, tickets. Writes: tickets.notes (append only).
    """
    con = _connect(write=True)
    try:
        result = ledger.add_payment_request(
            con, ticket_id, kind, ref_id, amount, account, reason, requested_by
        )
        if result.get("ok"):
            con.commit()
        return result
    finally:
        con.close()


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
    does not exist, the same request is already pending, or the account cannot cover
    the cost (pricing.unit_cost x qty). Returns a request_id a human can approve.
    Reads: desk, vendors, invoices, inventory, pricing, cash_accounts, tickets. Writes: tickets.notes (append only).
    """
    con = _connect(write=True)
    try:
        result = ledger.add_purchase_request(
            con, ticket_id, vendor_id, sku, size, qty, account, reason, requested_by
        )
        if result.get("ok"):
            con.commit()
        return result
    finally:
        con.close()


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
    ledger.ensure_working_copy()  # fresh clone: make data/campus_customs_new.db from the original
    mcp.run(show_banner=False)
