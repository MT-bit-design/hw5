# Campus Customs

Campus Customs is a small campus shop that sells shirts, hoodies, caps, and mugs. In this project, a team of five AI agents works the shop's open tickets: a customer order, a rent notice, and a bulk discount request. A person signs off on every payment.

There are three parts:

1. **MCP server** (`mcp_server/`): the only way the agents read or touch shop data. It works on a copy of the shop database, with 13 tools for stock, bills, cash, margins, drafts, and requests.
2. **FastAPI backend with five agents** (`backend/`): Boss, Inventory, Accounting, Facilities, and Customer Service, built with PydanticAI. They can hand work to each other. The backend runs them and gives the dashboard its API.
3. **React dashboard** (`frontend/`): a calm "desk" where you watch the five agents work, sign or decline payment slips, and see the cash balance.

## What you need

- Windows with Python 3.12 or newer and Node.js 20 or newer
- A Portkey API key with access to `gpt-6-luna`
- The course's shop database, `campus_customs.db` (it comes in the course's `data.zip`)

## Setup from a clean clone

Run these in a terminal (Command Prompt or PowerShell) from the project folder.

1. Make a Python virtual environment and install the packages. The venv must be called `.venv` and sit in the project folder.

   ```
   python -m venv .venv
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. Add your Portkey key. Copy the example file, then open `backend\.env` and put your key after `PORTKEY_API_KEY=`.

   ```
   copy backend\.env.example backend\.env
   ```

   `backend\.env` is ignored by git. Never commit it. If `PORTKEY_API_KEY` is also set as a system environment variable, that value is used first.

3. Put the shop database in `data\`. If you have the course's `data.zip`, put it in the project folder and unzip it there; it holds `data\campus_customs.db`. In PowerShell:

   ```
   Expand-Archive data.zip -DestinationPath .
   ```

   Or create a `data` folder and copy `campus_customs.db` into it. The result must be `data\campus_customs.db`.

   The agents never change that file. They work on a copy, `data\campus_customs_new.db`, which the backend (or the MCP server) makes automatically from the original the first time it starts. The **Reset desk** button makes a fresh copy at any time.

4. Install the dashboard packages:

   ```
   cd frontend
   npm install
   cd ..
   ```

## Start it (Windows)

Use two terminals.

**Backend** (from `backend\`):

```
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

It answers at http://localhost:8000. For example, http://localhost:8000/api/tickets lists the tickets.

**Dashboard** (from `frontend\`):

```
cd frontend
npm run dev
```

It opens http://localhost:5173 in your browser. Port 5173 must be free; the backend only accepts the dashboard from `localhost` / `127.0.0.1`.

**Optional, for Claude Code:** `.mcp.json` lets Claude Code use the MCP server directly. Open Claude Code in the project folder and approve the `campus-customs` server when it asks. It uses the same `.venv`.

## Using the board

1. **Pick a ticket** on the left. Open tickets show what they are waiting for ("Waiting for: …").
2. **Start the team.** Press "Start the team" (or "Continue" if the ticket was worked before and nothing is waiting). A run takes about 3 to 4 minutes. You can watch each agent think, use tools, and pass notes to the others.
3. **Approve or decline.** When an agent asks to pay something, a slip appears under "Waiting for your signature", showing the amount, who gets paid, and the cash after.
   - **Approve** pays it, and the balance drops.
   - **Decline** says no and moves no cash.
4. A ticket shows **Resolved** only when the backend says it is done.
5. **Reset desk** (bottom right, with a confirm) puts the tickets, cash, and requests back to the start. The activity log is kept.

Each run uses model tokens. Approve, Decline, and Reset do not.

## The rules

- **One model only:** `gpt-6-luna`, through Portkey. It is set in one place, `backend/config.py`.
- **A person approves every payment.** Agents can only ask. Only the Approve button pays.
- **No negative cash.** A payment or order is refused if the balance is too small. A sale we hope to make does not count as cash.
- **A vendor with an open unpaid invoice will not ship**, so no order goes to them.
- **Drafts only.** Agents never email, text, or call anyone. Customer replies are drafts saved on the ticket for a person to send.
- **Facts come only from the database** (through the MCP server), and the original database is never changed.

## Folder map

```
backend/          FastAPI app (main.py), the agent team (team.py), settings (config.py)
  agents/         one file per agent role
  prompts/        one prompt per agent
  .env.example    copy to .env and add your key
mcp_server/       MCP server (server.py) and the cash rules (ledger.py)
frontend/         React + Vite + TypeScript dashboard (src/api.ts holds the backend address)
data/             the shop database goes here (not in git)
output/           results and docs (below)
.mcp.json         lets Claude Code start the MCP server
requirements.txt  Python packages
AI_prompts.md     the prompts used to build this project
```

Files in `output/`:

| File | What it is |
|---|---|
| `desk_tickets.html` | The plan (Expected) and what really happened (Actual) for each ticket, plus the Cash and Reflection tabs. Opens with a double click. |
| `resolved_board.html` | Screenshots of the dashboard after each ticket resolved. Opens with a double click. |
| `resolved_tickets.json` | Each ticket's outcome, what each agent did, and every approval. |
| `audit_trail.json` | Every agent step from every run (model calls, tool calls, handoffs, answers, errors). It only grows. |
| `harness.md` | Technical notes: tables, MCP tools, agents, API routes, dashboard, safety rules, limits. |
| `design.md` | Why the dashboard looks and behaves the way it does. |
| `mcp_smoke.json` | The first live test of the MCP tools, checked against the database with SQL. |
| `screenshots/` | The three board screenshots used by `resolved_board.html`. |
