# Campus Customs Agent Harness

Five PydanticAI agents work the shop's tickets. They get facts only from an MCP server over a working copy of the shop database. A FastAPI backend runs them and a React board shows them. Money moves only when a person clicks Approve.

```
React board (frontend/, :5173) --HTTP--> FastAPI (backend/main.py, :8000) --> agent team (backend/team.py) --stdio--> MCP server (mcp_server/server.py) --> data/campus_customs_new.db
                                              \--> ledger (mcp_server/ledger.py): approve / decline / reset (human routes only)
```

## Data

- Original: `data/campus_customs.db`. Read-only, never changed.
- Working copy: `data/campus_customs_new.db`. All tools and routes use it. `POST /api/reset` copies the original over it.
- "Today" for everyone is `desk.date_today` (2026-08-31), not the system clock.
- Both databases are in git: the original, and the working copy in the final state of the Problem 9 run (checking $152, three payments). SQLite temp files (`*.db-journal`, `*.db-wal`, `*.db-shm`) and `*.zip` stay out.

## Tables

Row counts are at the start (right after a reset). Links marked *implied* are not declared foreign keys, so code joins on them by hand.

| Table | Rows | Fields | Why it matters |
|---|---|---|---|
| desk | 1 | `date_today`, `notes` | The shop's "today"; every due-date and overdue check uses it. |
| tickets | 3 | `id` (PK), `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id` (FK → leases), `invoice_id` (FK → invoices), `status`, `notes`, `created_at`. Links: `sku`+`size` → inventory, `sku` → pricing (*implied*) | The work queue. `status` is open or resolved. `notes` is the board: drafts, requests, and decisions are added here. |
| inventory | 10 | `sku` + `size` (PK), `name`, `qty`, `location`. Links: `sku` → pricing (*implied*) | Stock on hand by size; decides if an order can ship now. |
| pricing | 4 | `sku` (PK), `unit_cost`, `list_price` | Cost and price; `unit_cost` is the floor for any discount. |
| vendors | 3 | `id` (PK), `name`, `specialty`, `lead_days` | Who can restock and how long it takes. |
| invoices | 1 | `id` (PK), `vendor_id` (FK → vendors), `amount`, `due_date`, `status`, `description` | Money owed to vendors. A vendor with an open unpaid invoice will not ship. |
| leases | 1 | `id` (PK), `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes` | The real rent amount and date, to check a rent notice against. |
| cash_accounts | 1 | `name` (PK), `balance`, `date` | Cash available ($3,400 in checking at the start). It can never go below zero. |
| payments | 0 | `id` (PK), `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by`. Links: `ref_id` → invoices, leases, or vendors by `kind`; `account` → cash_accounts (*implied*) | Every payment a person approved, with who approved it. |

## MCP Tools

Server: `mcp_server/server.py` (FastMCP, stdio). This list was read live from the running server (13 tools). Every tool opens the working copy on each call, and nothing is hardcoded. Agents get shop facts only from here; there is no second tool layer.

| Tool | Reads | Writes | What it does |
|---|---|---|---|
| check_stock | inventory, pricing | none | Qty on hand for a SKU and size, the other sizes, price and cost |
| get_bills_and_cash | desk, leases, invoices, vendors, cash_accounts | none | Rent and unpaid invoices with days until due, cash, and cash left if all are paid |
| quote_bulk_order | desk, inventory, pricing, vendors | none | On hand vs. requested, shortfall, list and cost totals, max discount, vendor lead times |
| list_open_tickets | desk, tickets | none | Open tickets and their links |
| get_ticket | desk, tickets | none | One ticket, including the notes from earlier runs |
| find_restock_vendors | desk, inventory, vendors, invoices | none | Vendors for a SKU: lead time, ready-by date, and whether an unpaid invoice blocks them |
| get_invoice | desk, invoices, vendors, tickets | none | One invoice, days overdue, linked tickets |
| get_lease | desk, leases, tickets | none | One lease, days until rent is due, linked tickets |
| check_margin | pricing | none | Margin and discount for a proposed price; flags below cost |
| draft_customer_message | (tickets) | tickets.notes (append only) | Saves a draft reply. Never sends; refuses emails and phone numbers |
| request_payment | desk, invoices, leases, cash_accounts, tickets | tickets.notes (append only) | Asks a person to pay an invoice or rent. Refuses wrong amounts, paid bills, short cash, duplicates, and declined requests. Never pays |
| request_purchase_order | desk, vendors, invoices, inventory, pricing, cash_accounts, tickets | tickets.notes (append only) | Asks a person to approve a restock. Refuses a blocked vendor, short cash, duplicates, and declined requests. Never orders |
| record_decision | (tickets) | tickets.notes (append only) | Writes the Boss's final call on the board. The team runner calls it with the Boss's final answer |

No MCP tool writes to `payments` or `cash_accounts`, or changes stock or prices. The cash rules live once, in `mcp_server/ledger.py`, which both the request tools and the human routes use. `ledger.approve_request` and `ledger.decline_request` are not MCP tools, so agents cannot reach them.

## Agent Team

PydanticAI, code in `backend/`. Each role has a file in `backend/agents/` and a prompt in `backend/prompts/`. The data types are in `backend/models.py`, and the audited loop and `delegate` tool are in `backend/team.py`.

- **Model:** every agent uses one model, `gpt-6-luna`, set once in `backend/config.py`. It is called through Portkey's Responses API with `PORTKEY_API_KEY` from `backend/.env`. The provider reports its deployment as `gpt-6-luna-global`, and the audit logs `model` and `served_model` separately.
- **Delegation:** every agent has a `delegate` tool and can hand work to any other. Each agent sees only its own MCP tools.

| Agent | Job | MCP tools |
|---|---|---|
| Boss | Reads the ticket and the notes from earlier runs, routes the work, makes the final call | list_open_tickets, get_ticket (its final answer is recorded with record_decision by the runner) |
| Inventory | Stock by SKU and size, shortfalls, which vendor can restock and how fast | get_ticket, check_stock, quote_bulk_order, find_restock_vendors |
| Accounting | Cash, invoices, margins; files payment and purchase order requests for a person to approve | get_ticket, get_bills_and_cash, get_invoice, check_margin, quote_bulk_order, find_restock_vendors, request_payment, request_purchase_order |
| Facilities | The lease and rent; checks a rent notice against the lease | get_ticket, get_lease, get_bills_and_cash |
| Customer Service | Draft replies to customers; drafts stay on the board | get_ticket, check_stock, draft_customer_message |

### When a ticket resolves

1. The Boss has recorded a decision on it.
2. No payment or purchase request on it is still pending. Declined requests never hold a ticket open.
3. For a `customer_order` that is short on stock only: a person has approved or declined a restock purchase order for that SKU and size. Paying the vendor's invoice alone is not enough.

Other ticket types, like the `price_override` on 103, can resolve with an honest partial answer. An open ticket can be run again ("Continue"): the Boss reads the notes, skips finished work, and picks up the next step.

### Requests

Requests are stored as one line each in `tickets.notes`:

```
[REQUEST R102-1 | PENDING | date | by agent] kind=... amount=... account=... :: text
```

Approval changes the status to `APPROVED by <name> on <date>`; a decline changes it to `DECLINED by <name> on <date>`. On approval:
- cash goes down;
- a `payments` row is added with `approved_by`;
- an invoice becomes `paid`, or the lease's `next_due` moves forward one month;
- a purchase order adds no stock, because goods have not arrived.

## API Routes

FastAPI in `backend/main.py` (this list was read from the code). Start it from `backend/` with:

```
..\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

CORS allows only `http://localhost` and `http://127.0.0.1` origins (the React dev server).

- `GET /api/tickets`: the tickets with their real `tickets.status`, `has_decision`, `pending_requests`, `open_because`, and `last_decision` (the Boss's latest recorded decision), plus the run state (`run.running`, `run.last_run`).
- `POST /api/tickets/{ticket_id}/run`: starts the team on one ticket in the background and returns a `run_id` right away (202). Refuses if a run is going or the ticket is resolved.
- `GET /api/events?ticket=&limit=&run_id=`: agent events from the audit trail, newest first. Defaults to the latest run. The key, emails, and phones are scrubbed.
- `GET /api/requests?status=pending|approved|declined|all`: payment and purchase order requests with their `payee`.
- `POST /api/requests/{request_id}/approve` (body `{"approved_by": "name"}`): the only route that moves cash. Refuses if the request is not pending, cash is short, the vendor has an open unpaid invoice, or the approver is an agent.
- `POST /api/requests/{request_id}/decline` (body `{"declined_by": "name", "reason": "..."}`): moves no cash; only the request status changes. Refuses if the request is not pending, or the decliner is an agent.
- `GET /api/cash`: the checking balance from `cash_accounts`.
- `POST /api/reset`: copies the original over the working copy. Refuses while a run is going. Keeps the audit trail.

## Dashboard

React + Vite + TypeScript in `frontend/`. From `frontend/`, run `npm install`, then `npm run dev`. It opens http://localhost:5173 (`strictPort`); `?ticket=101` opens it on one ticket. Design notes are in `output/design.md`.

- The backend address lives only in `src/api.ts` (`VITE_API_URL`, see `frontend/.env.example`). The frontend holds no keys.
- It polls every 2 s during a run, every 8 s when idle, and every 5 s when the backend is down. Start, Approve, Decline, and Reset lock while a run goes.
- It shows a ticket as Resolved only when the backend says so. Approve and Decline are always a person's click, signed "MT".
- A run that failed shows one plain line (for example, "This run stopped: the AI service had an error (HTTP 500). Nothing was paid.") instead of the raw error. If that run never reached a decision, the Boss seat shows the last recorded decision, labelled "from an earlier run".

## Audit Trail

`output/audit_trail.json` is a JSON array that only grows. Each run appends, and nothing is wiped, not even by reset. Each agent-loop step is one row: time, run_id, ticket, agent, depth, step, step_type (`model_call`, `tool_call`, `handoff`, `answer`, `limit_stop`, `error`), tool and inputs, a result summary, handoff from/to, `model`, `served_model`, and tokens. The API key, emails, phone numbers, and customer names are scrubbed before writing.

## Safety

Guardrails for agents that touch real customers and real money:
- **People approve money.** Agents can only ask. No agent can pay, order, mark a bill paid, approve, or decline. Only the human Approve and Decline routes can.
- **No negative cash.** Requests and approvals are refused when cash is short. Hoped-for sales never count as cash.
- **Checked amounts.** A payment must match the real invoice or rent. A paid bill, a duplicate, or a request a person declined cannot be filed again.
- **Vendor rule in code.** No purchase order goes to a vendor with an open unpaid invoice.
- **Nothing leaves the shop.** Customer replies are drafts on the board with no emails or phone numbers. Nobody contacts customers, vendors, or the landlord.
- **Least privilege.** Each agent sees only its MCP tools. The MCP server starts without the API key in its environment.
- **One working database.** The original is never written. A run can be undone with Reset.
- **Facts come from tools.** The prompts forbid made-up data and contain no shop numbers.
- **Audit everything, leak nothing.** Every step is logged and scrubbed.
- **Fail safe.** When the model provider fails, the run stops, an `error` row is logged, the ticket stays open, and nothing is paid. In Problem 9, 4 of 7 runs hit provider errors, and none moved money.

Limits that keep token use in check (all in `backend/config.py`):
- Delegation depth at most 2. At most 60 steps (model calls plus tool calls) per ticket.
- PydanticAI `UsageLimits`, shared by all agents on a ticket: 30 model requests, 40 tool calls, 100,000 total tokens.
- At most 4,000 output tokens per reply (reasoning included), with low reasoning effort.
- 120 s per model request, and 30 s for the MCP server to start.
- Short structured answers (`AgentReply`), no self-delegation, and no repeated questions. When a limit is hit, the run stops with a `limit_stop` row and the ticket goes to a person.
