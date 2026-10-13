# AI Prompts Log

A log of the prompts I typed to Claude Code, one section per problem, kept exactly as typed.

## Problem 1 - Vibe coder prompts

### Prompt

````text
Problem 1: Vibe coder prompts.
Make a file called `AI_prompts.md` in the project root. It’s a log of what I type to you, so keep my prompts exactly as I type them.
Give each problem its own section with:

* the problem number and title
* the prompt I typed
* a follow-up prompt, only if I needed one, plus one sentence on what was missing after the first try

Add a new section every time I start a new problem, so the file keeps growing.
Log this prompt as “Problem 1 - Vibe coder prompts.” Then make a git commit named “Problem 1 - Vibe coder prompts.”
````

### Follow-up

None.

## Problem 2 - Study the Campus Customs database

### Prompt

````text
Problem 2: Study the Campus Customs database.
If `data.zip` isn’t unzipped yet, unzip it so I have `data/campus_customs.db`.

1. Open `data/campus_customs.db` in read-only mode and look at every table. For each one, find the fields, the keys, how it links to other tables, and the row count.
2. Copy the file to `data/campus_customs_new.db`. This is the working copy that later problems will change. Never change the original.
3. Look at the three open tickets and find how each one links to other tables, like inventory, pricing, vendors, invoices, leases, and cash accounts. Also note what `desk.date_today` says.
4. Start `output/harness.md`. For each table, list the fields and write one short line on why the table matters for the agents. I’ll keep adding to this file in later problems.

Keep the harness short and simple. This repo will be public, so don’t put any customer emails, phone numbers, or other personal details in it. Describe the fields only.
Log this prompt in `AI_prompts.md` as “Problem 2 - Study the Campus Customs database.” Commit it as “Problem 2 - Study the Campus Customs database.” Don’t commit `data/` or any `.db` file.
````

### Follow-up

None.

## Problem 3 - Build the MCP server

### Prompt

````text
Problem 3: Build the MCP server.

Make an MCP server in mcp_server/ using FastMCP. It reads data/campus_customs_new.db. You do not need to run it.

Write three read-only tools for the three open tickets (101, 102, 103). Look at the tickets and the database first, then pick the three tools that unlock them. Give each tool a clear name.

Rules:
- Only use data from the database. Never make up data.
- Read the database inside each tool call. Do not hardcode any values.
- Do not touch data/campus_customs.db.
- Do not add any AI calls yet.

Then:
1. In output/harness.md, add a section for the MCP tools. For each tool, write: the table it reads, which ticket it helps (101, 102 or 103), and one sentence on why it is the right tool for that ticket. Name the real ticket facts, so it does not sound vague.
2. Write a short mcp_server/README.md: what the server is for, which database file it uses, and the three tools.
3. Add a Problem 3 section to AI_prompts.md.
4. Commit as "Problem 3 - Build the MCP server". Do not push.

When done, show me git status and git log.
````

### Follow-up

None.

## Problem 4 - Add the MCP server to the vibe coder and test it

### Prompt

````text
Problem 4: Add the MCP server to the vibe coder and test each tool.

1. Add my MCP server to this project so you can call the tools. Save it in .mcp.json at the project root (project scope). Use relative paths only. No personal paths, no keys, nothing secret in the file.
2. If you need me to restart you or approve the server, tell me what to do, then wait.
3. When it is connected, test all three tools by really calling them through the MCP connection. Do not just run the Python code by hand.
4. For each tool, check the output against data/campus_customs_new.db with a plain SQL query. The values must match.
5. Save the evidence in output/mcp_smoke.json. For each tool include: the prompt I asked you, the tool name, and the tool output.
6. Add a Problem 4 section to AI_prompts.md.
7. Commit as "Problem 4 - Add the MCP server to the vibe coder and test it". Do not push.

When done, show me git status, git log, and the contents of output/mcp_smoke.json.
````

### Follow-up

````text
can you do all of this in a new HW5 folder. so the HW4 remains untoched
````

After the first try the MCP server could not connect, because the Claude Code session was still running in the HW4 folder, so it never loaded HW5's `.mcp.json`.

## Problem 5 - Build the agent team and grow the MCP tools

### First version (I stopped it with "wait" before any work started)

````text
Problem 5: Build the agent team and grow the MCP tools. build the agentic team for campus customs using pydanticAI: Boss, Inventory, Accounting, Facilities, and Customer Service. include prompts, models and agent loops so they can delegate work to each other with full connectivity. put the agent prompts in backend/prompts/ - one file per agent. put the data types in backend/models.py and the agent files under backend/ (the layout can vary as long as the five roles are clear). use the PORTKEY_API_KEY and only gpt-6-luna for every agent. write each prompt with my own words with the shop rules that agent needs. more detailed prompts that cover all aspects of an agent's work and scope will score higher than a short generic prompt. add any tools the agents need to your MCP server so they can work on the open tickets. shop facts come from the MCP server over data/campus_customs_new.db - do not invent a second shop-tools layer that bypasses MCP. wire the agents so they append to output/audit_trail.json as they run: for each agent-loop step, record enough to audit later. append to this file - do not wipe it each run. in output/harness.md, list each agent and each MCP tool (including ones you add in this problem) along with which table the tool uses. also add a short safety section: the guardrails a real business would want when agents touch real customers and real money, plus limits that keep token use in check. update mcp
````

````text
wait
````

### Prompt

````text
Problem 5: Build the agent team and grow the MCP tools.

Build the Campus Customs agent team with PydanticAI. Five agents: Boss, Inventory, Accounting, Facilities, Customer Service.

Code:
- Agent files in backend/. Data types in backend/models.py.
- One prompt file per agent in backend/prompts/.
- Every agent uses only gpt-6-luna through Portkey with PORTKEY_API_KEY. Put the model name in one place only. Never print the key. It lives in backend/.env, and .env stays out of git.
- Full connectivity: any agent can hand work to any other agent. Give each agent a delegate tool. Add safe limits: max delegation depth, max steps per ticket, and PydanticAI usage limits so nothing loops forever or burns tokens.
- Agents get shop facts only through the MCP server on data/campus_customs_new.db. Do not build a second tool layer that skips MCP.

Agent jobs, in my words:
- Boss reads each ticket, picks who works on it, and makes the final call.
- Inventory checks stock by SKU and size, finds shortfalls, and finds which vendor can restock.
- Accounting watches cash and invoices, checks margins, and prepares payments or purchase orders for a human to approve.
- Facilities handles shop space, leases and rent.
- Customer Service writes drafts to customers.

Shop rules to put in the prompts (each agent gets the ones it needs):
- desk.date_today is today. Use it for what is overdue.
- Vendor lead times come from the vendors table.
- A vendor will not ship while they have an open unpaid invoice.
- Any payment needs human approval. Agents can only ask for it.
- If cash is short, refuse. No negative balance. Cash only goes out, nothing comes in.
- Never email customers or call vendors. Drafts stay on the board.

Make each prompt detailed: the agent's job, what it can and cannot do, which tools to use and when, when to hand off, and how to answer. Write it in plain simple words like I write. Never make up data.

MCP tools: keep my three tools. Add what the agents need to work tickets 101, 102 and 103. For example: vendor and lead time for a SKU, a way to draft a customer message, and a way to ask for a payment. If a payment tool is added, it must refuse without a human approval and refuse if cash is short. Agents cannot approve their own payments. Use only existing tables. If you need a new table, stop and ask me.

Audit trail: append to output/audit_trail.json every agent-loop step. Do not wipe it on a new run. Each step: time, ticket, agent, step type (model call, tool call, handoff, answer), tool name and inputs, result summary, who handed to whom, model name, and token use. Leave out the API key and any customer email or phone, because the repo is public.

Docs:
- output/harness.md: list each agent, and each MCP tool (old and new) with the table it uses. Add a short safety section: guardrails a real business needs when agents touch real customers and money, plus the limits that keep token use down.
- Update mcp_server/README.md so the tool list matches.
- Add a Problem 5 section to AI_prompts.md.

Test: run one small test on ticket 101 so the audit trail has real rows. No payments. Then reset data/campus_customs_new.db from the original. If the key is missing, tell me and stop.

Check: show me that gpt-6-luna is the only model name in the code. Commit as "Problem 5 - Build the agent team and grow the MCP tools". Do not push.

When done, show me git status, git log, the MCP tool list, and the first few rows of audit_trail.json.
````

### Follow-up

None.
