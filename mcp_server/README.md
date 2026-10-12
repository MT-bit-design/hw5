# Campus Customs MCP Server

A small [FastMCP](https://gofastmcp.com) server that gives agents read-only access to the Campus Customs shop data, so they can work the open tickets using only facts from the database.

## Database

- Reads `data/campus_customs_new.db` (the working copy), opened in SQLite read-only mode on every tool call.
- Never touches the original `data/campus_customs.db`.
- "Today" comes from `desk.date_today`, not the system clock.

## Tools

| Tool | Reads | What it returns |
|---|---|---|
| `check_stock(sku, size)` | inventory, pricing | Qty on hand and location for that size, the other sizes in stock, list price and unit cost. |
| `get_bills_and_cash()` | desk, leases, invoices, vendors, cash_accounts | Rent and unpaid invoices with days until due (negative = overdue), cash balances, and cash left if everything is paid. |
| `quote_bulk_order(sku, size, qty)` | desk, inventory, pricing, vendors | On hand vs. requested and the shortfall, list and cost totals, the max discount before selling at a loss, and vendor lead times. |

## Run

```bash
pip install -r mcp_server/requirements.txt
python mcp_server/server.py
```
