# Campus Customs Agent Harness

## Data

- Original: `data/campus_customs.db` (read-only, never change it)
- Working copy: `data/campus_customs_new.db` (agents write here)
- "Today" for every agent is `desk.date_today`, not the system clock.

## Tables

Links marked *implied* are not declared foreign keys; agents must join on them by hand.

### desk (1 row)
- Fields: `date_today`, `notes`
- Why: The shop's current date; all due-date and overdue checks use it.

### tickets (3 rows)
- Fields: `id` (PK), `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id` (FK → leases), `invoice_id` (FK → invoices), `status`, `notes`, `created_at`
- Links: `sku` + `size` → inventory (*implied*), `sku` → pricing (*implied*)
- Why: The work queue; each ticket is a job an agent must resolve.

### inventory (10 rows)
- Fields: `sku` + `size` (composite PK), `name`, `qty`, `location`
- Links: `sku` → pricing (*implied*)
- Why: Stock on hand by size; decides if an order can ship now.

### pricing (4 rows)
- Fields: `sku` (PK), `unit_cost`, `list_price`
- Why: Cost and price per SKU; sets the floor for any discount.

### vendors (3 rows)
- Fields: `id` (PK), `name`, `specialty`, `lead_days`
- Why: Who can restock or deliver, and how long it takes.

### invoices (1 row)
- Fields: `id` (PK), `vendor_id` (FK → vendors), `amount`, `due_date`, `status`, `description`
- Why: Money the shop owes vendors; must be checked before paying.

### leases (1 row)
- Fields: `id` (PK), `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes`
- Why: Rent the shop owes; the real amount and date to check a rent notice against.

### cash_accounts (1 row)
- Fields: `name` (PK), `balance`, `date`
- Why: Cash available; every payment must fit inside the balance.

### payments (0 rows)
- Fields: `id` (PK), `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by`
- Links: `ref_id` → invoices or leases depending on `kind` (*implied*), `account` → cash_accounts.name (*implied*)
- Why: The record of money paid out, with who approved it; empty at the start.

## MCP Tools

Server: `mcp_server/server.py` (FastMCP). These first three tools are read-only and query `data/campus_customs_new.db` on every call. The full list is under "MCP Tools: Full List" below.

### check_stock(sku, size)
- Reads: inventory, pricing
- Helps: ticket 101
- Why: The customer wants one Classic Bulldog Tee in size S, and this tool shows size S has 0 on hand while M, L, and XL are in stock, so the agent can't promise shipment and can offer another size or a restock.

### get_bills_and_cash()
- Reads: desk, leases, invoices, vendors, cash_accounts
- Helps: ticket 102
- Why: The rent notice says rent is due in 2 days, and this tool confirms against the lease that $2,400 is due 2026-09-02, shows $3,400 in checking, and surfaces the overdue $840 Bulldog Print Co invoice that would leave only $160 if both are paid.

### quote_bulk_order(sku, size, qty)
- Reads: desk, inventory, pricing, vendors
- Helps: ticket 103
- Why: The club wants 20 navy hoodies in size M at a discount, and this tool shows only 8 are on hand (12 short, Bulldog Print Co lead time 5 days) and that unit cost is $22 against a $58 list price, so any discount must stay above cost.

## Agent Team

PydanticAI, code in `backend/`. Run one ticket with `python -m backend.run 101`.
Every agent uses the one model set in `backend/config.py`, through Portkey with `PORTKEY_API_KEY` from `backend/.env`.
Every agent has a `delegate` tool, so any agent can hand work to any other. Each agent sees only its own MCP tools.

| Agent | Role file / prompt | Job | MCP tools |
|---|---|---|---|
| Boss | `agents/boss.py`, `prompts/boss.md` | Reads the ticket, routes the work, makes and records the final call | list_open_tickets, get_ticket, record_decision |
| Inventory | `agents/inventory.py`, `prompts/inventory.md` | Stock by SKU and size, shortfalls, which vendor can restock | get_ticket, check_stock, quote_bulk_order, find_restock_vendors |
| Accounting | `agents/accounting.py`, `prompts/accounting.md` | Cash, invoices, margins; prepares payment and purchase order requests for a human | get_ticket, get_bills_and_cash, get_invoice, check_margin, quote_bulk_order, find_restock_vendors, request_payment, request_purchase_order |
| Facilities | `agents/facilities.py`, `prompts/facilities.md` | Shop space, lease, rent; checks a rent notice against the lease | get_ticket, get_lease, get_bills_and_cash |
| Customer Service | `agents/customer_service.py`, `prompts/customer_service.md` | Writes draft replies that stay on the board | get_ticket, check_stock, draft_customer_message |

Data types live in `backend/models.py`. The audited agent loop and `delegate` live in `backend/team.py`.

## MCP Tools: Full List

The agents get shop facts only from this server. There is no second tool layer.

| Tool | Tables | New in P5 | What it does |
|---|---|---|---|
| check_stock | inventory, pricing | | Qty on hand for a SKU and size, other sizes, price and cost |
| get_bills_and_cash | desk, leases, invoices, vendors, cash_accounts | | Rent, unpaid invoices, days until due, cash, and cash left after paying everything |
| quote_bulk_order | desk, inventory, pricing, vendors | | On hand vs. requested, shortfall, list and cost totals, max discount, vendor lead times |
| list_open_tickets | desk, tickets | yes | Open tickets and their links |
| get_ticket | desk, tickets | yes | One ticket, including the notes already on the board |
| find_restock_vendors | desk, inventory, vendors, invoices | yes | Vendors for a SKU: lead time, ready-by date, blocked by an unpaid invoice or not |
| get_invoice | desk, invoices, vendors, tickets | yes | One invoice, days overdue, linked tickets |
| get_lease | desk, leases, tickets | yes | One lease, days until rent is due, linked tickets |
| check_margin | pricing | yes | Margin and discount for a proposed price; flags below cost |
| draft_customer_message | tickets (append note) | yes | Saves a draft reply on the ticket. Never sends. Refuses emails and phone numbers |
| request_payment | desk, invoices, leases, cash_accounts, payments, tickets (append note) | yes | Asks a human to pay an invoice or rent. Refuses wrong amounts, already-paid bills, short cash, and duplicates. Never pays |
| request_purchase_order | desk, vendors, invoices, inventory, pricing, cash_accounts, tickets (append note) | yes | Asks a human to approve a restock. Refuses a vendor with an open unpaid invoice, short cash, and duplicates. Never orders |
| record_decision | tickets (append note) | yes | Boss writes the final call on the board |

No tool writes to `payments` or `cash_accounts`, or changes stock or prices. Money only moves when a human approves outside the agent system.

## Audit Trail

`output/audit_trail.json` is a JSON array that only grows; each run appends and nothing is wiped.
Each agent-loop step is one row: time, run_id, ticket, agent, depth, step number, step_type (`model_call`, `tool_call`, `handoff`, `answer`, plus `limit_stop` and `error`), tool and inputs, a result summary, handoff from/to, model, and tokens.
Before writing, rows are scrubbed of the API key, emails, phone numbers, and customer names seen on customer tickets.

## Safety

Guardrails for agents that touch real customers and real money:
- **People approve money.** Agents can only ask. No agent tool pays, orders, or marks a bill paid, and no agent can approve its own request.
- **No negative cash.** Payment and order requests are refused if they are more than the balance. Expected sales do not count as cash.
- **Checked amounts.** A payment request must match the real invoice or rent, cannot be for a bill already paid, and cannot repeat a request already waiting.
- **Vendor rule in code.** A purchase order to a vendor with an open unpaid invoice is refused.
- **Nothing leaves the shop.** Customer replies are drafts on the board, with no email or phone numbers allowed. Nobody contacts vendors or the landlord.
- **Least privilege.** Each agent sees only the MCP tools for its job. The MCP server is started without the API key in its environment.
- **One database, never the original.** The server only opens `campus_customs_new.db`. A run can be undone by copying the original back.
- **Facts come from tools.** The prompts forbid made-up data, and the prompts contain no shop numbers to copy from.
- **Audit everything, leak nothing.** Every step is logged, and the key and personal details are scrubbed.

Limits that keep token use in check (all in `backend/config.py`):
- Delegation depth: at most 2 levels (Boss, then a specialist, then one more).
- Steps per ticket: at most 60 model calls plus tool calls across all agents.
- PydanticAI `UsageLimits`, shared by every agent on a ticket: 30 model requests, 40 tool calls, 100,000 total tokens.
- At most 2,000 output tokens per reply, with low reasoning effort.
- Short, structured answers (`AgentReply`), no self-delegation, and the prompts say not to ask the same question twice.
- When a limit is hit, the run stops cleanly, a `limit_stop` row is logged, and the ticket is handed to a human.
