"""Campus Customs MCP server: read-only tools for the open tickets.

Every tool opens data/campus_customs_new.db in read-only mode on each call,
so answers always reflect the current working copy and nothing is hardcoded.
"""

import sqlite3
from datetime import date
from pathlib import Path

from fastmcp import FastMCP

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "campus_customs_new.db"

mcp = FastMCP("campus-customs")


def _connect() -> sqlite3.Connection:
    """Open the working copy read-only; fails if the file is missing."""
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _today(con: sqlite3.Connection) -> date:
    return date.fromisoformat(con.execute("SELECT date_today FROM desk").fetchone()["date_today"])


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


for _tool in (check_stock, get_bills_and_cash, quote_bulk_order):
    mcp.tool(_tool)


if __name__ == "__main__":
    mcp.run()
