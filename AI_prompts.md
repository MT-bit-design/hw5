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
