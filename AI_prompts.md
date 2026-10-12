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
