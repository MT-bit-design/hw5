# Campus Customs MCP Server

A small [FastMCP](https://gofastmcp.com) server, and the only way the Campus Customs agents get shop facts. It reads the shop database and gives each agent the tools for its job. Read tools never change anything. Board tools only add a note to a ticket. No tool moves money.

## Database

- Uses `data/campus_customs_new.db` (the working copy) and opens it fresh on every tool call.
- Never touches the original `data/campus_customs.db`. To undo a run, copy the original over the working copy.
- "Today" comes from `desk.date_today`, not the system clock.

## Tools

### Read (no changes)

| Tool | Tables | What it returns |
|---|---|---|
| `check_stock(sku, size)` | inventory, pricing | Qty on hand and location for that size, other sizes, list price and unit cost |
| `get_bills_and_cash()` | desk, leases, invoices, vendors, cash_accounts | Rent and unpaid invoices with days until due, cash balances, cash left if everything is paid |
| `quote_bulk_order(sku, size, qty)` | desk, inventory, pricing, vendors | On hand vs. requested, shortfall, list and cost totals, max discount before a loss, vendor lead times |
| `list_open_tickets()` | desk, tickets | Open tickets and their links |
| `get_ticket(ticket_id)` | desk, tickets | One ticket with all fields and the notes on the board |
| `find_restock_vendors(sku)` | desk, inventory, vendors, invoices | Each vendor's lead time, ready-by date, and whether an open unpaid invoice blocks it |
| `get_invoice(invoice_id)` | desk, invoices, vendors, tickets | One invoice, days overdue, linked tickets |
| `get_lease(lease_id)` | desk, leases, tickets | One lease, days until rent is due, linked tickets |
| `check_margin(sku, unit_price, qty)` | pricing | Discount off list, margin per unit and in total, below-cost flag |

### Board (append a note to the ticket only)

| Tool | Tables | What it does |
|---|---|---|
| `draft_customer_message(ticket_id, message, written_by)` | tickets | Saves a draft reply. Never sends. Refuses emails and phone numbers |
| `request_payment(ticket_id, kind, ref_id, amount, account, reason, requested_by)` | desk, invoices, leases, cash_accounts, payments, tickets | Asks a human to pay an invoice or rent. Refuses a wrong amount, an already-paid bill, short cash, or a duplicate. Never pays |
| `request_purchase_order(ticket_id, vendor_id, sku, size, qty, account, reason, requested_by)` | desk, vendors, invoices, inventory, pricing, cash_accounts, tickets | Asks a human to approve a restock. Refuses a vendor with an open unpaid invoice, short cash, or a duplicate. Never orders |
| `record_decision(ticket_id, decision, decided_by)` | tickets | Records the Boss's final call |

## Run

```bash
pip install -r requirements.txt
python mcp_server/server.py
```

Claude Code picks it up from `.mcp.json`. The agent team starts it on its own over stdio (`backend/team.py`).
