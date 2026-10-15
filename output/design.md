# The Desk: Design Notes

The dashboard in `frontend/` is a calm desk where five colleagues work together. You sit at the head of it. They do the work, and you sign.

## Layout

- **Top:** the name of the place ("The desk"), one quiet line on what it is, and on the right the checking balance as one big number.
- **Left rail ("On the desk"):** the open tickets as soft cards. Each shows its type, subject, item, and one plain line: "Waiting for: …" (from the backend's `open_because`). Resolved tickets move below into a **Done** row.
- **Main area, top to bottom:**
  1. The chosen ticket's title, what it is waiting for, and one button: "Start the team", "Continue", "Waiting for you", or "The team is working…".
  2. **The desk:** a light grey table top with five seats. The Boss sits at the head in a wide seat. Inventory, Accounting, Facilities, and Customer Service sit in a row below.
  3. **Waiting for your signature:** payment and order slips.
  4. **What each colleague did:** a short summary per agent.
- **Footer:** the team's names and a small "Reset desk" button with a confirm step.

There is lots of white space, one column of attention at a time, and nothing blinks unless someone is working.

## How the agents read differently

- **One calm main color** (a deep teal) for the Boss, the cash, and the main buttons.
- **One soft color per colleague:** sage for Inventory, warm amber for Accounting, slate blue for Facilities, rose for Customer Service. Each seat has a thin colored top edge, a round initial, and a tinted "note" area.
- **Each has a voice line** under the name: the Boss "Decides", Inventory "Counts the shelves", Accounting "Weighs the money", Facilities "Keeps the space", Customer Service "Writes to customers".
- **The Boss speaks in decisions.** The Boss's seat is wide and shows the final call as a short quote, with a "Next for you" box when you must act. The answer arrives as JSON from the backend, so the board turns it into plain text.
- **The others speak in what they are doing,** like "Thinking… next: checked stock" or "Asked you to pay (R102-1)."
- **The active colleague glows softly** in their own color, with a slow breathing glow. A colleague waiting on someone else says "Waiting on a colleague".
- **Tool calls are small chips** in the colleague's tint, like "read the lease" or "asked you to pay · R102-1". A refused call turns amber and says "refused".
- **A handoff is a note sliding in:** when the Boss asks Accounting for something, a small "Note from Boss" card slides into Accounting's seat.

Everything on the seats comes from `GET /api/events`. The board makes no model calls.

## Resolved tickets and cash

- **Resolved only when the backend says so.** A ticket shows a quiet, slightly tilted "Resolved" stamp, and moves into the Done row, only when `tickets.status` is `resolved`. The board never guesses.
- **"Waiting for you"** appears in amber on the ticket card, the ticket button, and every slip, whenever a request waits for your signature.
- **Approval slips look like paper:** a warm off-white card with the amount in large type, who gets paid, what it is for, the account, the cash after, and who asked. Approve and Decline sit side by side. Approve is the strong filled button, and Decline is quiet. A dashed line and "Signed, MT" sit at the bottom, like a signature line. Decline takes an optional reason.
- **Cash drops only after Approve.** It is one big calm number from `GET /api/cash`. After an approval it counts down smoothly to the new amount and leaves a small trail: "was ~~$3,400~~ · $2,400 paid out". Declining moves no cash, so the number stays still.
- **Refusals in plain words.** If the backend says no (cash short, not pending, vendor blocked), the board shows its reason as a simple banner.
- **Failures in plain words.** A run that hit an AI service error shows one calm line ("This run stopped: … Nothing was paid."), not raw error text. The Boss seat then shows the last decision from an earlier run, clearly labelled, so you still see what was decided.

**Why:** money and customers are the two places where a mistake is real. So those are the only places that ask for your hand, and they look the most like real paper. Everything else stays quiet so those moments stand out.

## States

- **Loading:** "Setting out the chairs…"
- **Empty:** "Nothing open", "No payments or orders are waiting", and "The team has not worked this ticket since the desk was reset".
- **Backend not running:** a soft amber banner with the exact start command. The board keeps trying every 5 seconds and reconnects on its own.
- **While a run goes:** the board polls every 2 seconds and locks Start, Approve, Decline, and Reset. Idle, it polls every 8 seconds.
- **Old runs:** the audit trail keeps every run, even from before a reset. The board only treats a run as current if the ticket has a decision now, or it is the run the backend just did. You can still open the older run with a quiet link.

## Care

- White background, Calibri (then Carlito, then sans-serif), dark grey ink with good contrast.
- Every control is a real button or input. You can tab through everything, focus rings are visible, Escape closes the reset confirm, and screen readers hear run and cash updates.
- `prefers-reduced-motion` turns off the glow, the sliding notes, and the cash count-down. Numbers just change.
- No keys live in the frontend. The backend address comes from `VITE_API_URL` in one file, `src/api.ts`.

## What I took from your sites

I could read three of the four sites as text only, so these notes are about feel, not pixels. **Claude's design interface returned "403 Forbidden" to my fetch tool, so I could not look at it.** I used only its general reputation: warm, unhurried, and conversational.

- **Renaissance Philanthropy:** editorial calm, generous white space, oversized figures for key numbers, and gentle motion that explains instead of decorates. This became the big light-weight cash number and the slow glow.
- **Mubadala Capital:** a confident vertical rhythm, and restrained, modular cards with one clear action each. This became the ticket cards and the one button per ticket.
- **quartey.com:** a minimal, personal, stacked index with lots of breathing room and small, friendly feedback. This became the left rail, the plain-word states, and the small human touches ("Setting out the chairs…", "Signed, MT").

I copied no logo, text, image, or layout from any of them.

## Creative choices

- **A desk, not a dashboard.** No charts, no sidebar of icons. The five seats make the delegation visible: you can see who is talking to whom.
- **Paper for money.** Slips and stamps borrow from real office paper, so the moments that need you feel different from the moments that do not.
- **Calm by default.** Motion only happens when something changes: a note arrives, a colleague starts working, or cash moves.
