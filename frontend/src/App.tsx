import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, API_URL, OfflineError, plainError } from "./api";
import type { AgentEvent, CashResponse, PayRequest, RunSnapshot, Ticket } from "./types";
import { AGENTS, SEAT_ORDER, TICKET_TYPE_LABEL } from "./lib/agents";
import { deriveDesk, parseReply, summarize } from "./lib/events";
import { money, timeAgo } from "./lib/format";
import { Cash } from "./components/Cash";
import { Seat } from "./components/Seat";
import { Tickets } from "./components/Tickets";
import { Slips } from "./components/Slips";
import { Summary } from "./components/Summary";
import { ResetDesk } from "./components/ResetDesk";

const ME = "MT";
const POLL_RUNNING_MS = 2000;
const POLL_IDLE_MS = 8000;
const POLL_OFFLINE_MS = 5000;

type Notice = { tone: "ok" | "warn"; text: string } | null;

export default function App() {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [run, setRun] = useState<RunSnapshot>({ running: false, last_run: null });
  const [events, setEvents] = useState<AgentEvent[]>([]); // newest first, from the backend
  const [eventsRunId, setEventsRunId] = useState<string | null>(null);
  const [requests, setRequests] = useState<PayRequest[]>([]);
  const [cash, setCash] = useState<CashResponse | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [starting, setStarting] = useState(false);
  const [showOldRun, setShowOldRun] = useState(false);

  const selectedRef = useRef<number | null>(null);
  selectedRef.current = selected;
  const wasRunning = useRef(false);
  const offlineRef = useRef(offline);
  offlineRef.current = offline;

  const loadEvents = useCallback(async (ticket: number | null, runId?: string) => {
    if (ticket === null) return;
    const ev = await api.events({ ticket, limit: 400, runId });
    if (ticket !== selectedRef.current) return; // the user picked another ticket meanwhile
    setEvents(ev.events);
    setEventsRunId(ev.run_id);
  }, []);

  const loadMoney = useCallback(async () => {
    const [req, c] = await Promise.all([api.requests("pending"), api.cash()]);
    setRequests(req.requests);
    setCash(c);
  }, []);

  /** One poll: tickets + run state, then whatever the current moment needs. */
  const poll = useCallback(async (): Promise<boolean> => {
    try {
      const t = await api.tickets();
      setTickets(t.tickets);
      setRun(t.run);
      setOffline(false);
      setLoadError(null);
      const running = t.run.running;
      const runTicket = t.run.last_run?.ticket ?? null;
      if (selectedRef.current === null) {
        const first = (running && runTicket) || t.tickets.find((x) => x.status !== "resolved")?.id || t.tickets[0]?.id || null;
        setSelected(first);
        selectedRef.current = first;
      } else if (running && runTicket !== null && !wasRunning.current) {
        setSelected(runTicket); // follow the team to the ticket it is working on
        selectedRef.current = runTicket;
      }
      const live = running && runTicket === selectedRef.current ? t.run.last_run?.run_id : undefined;
      await loadEvents(selectedRef.current, live);
      if (!running || !wasRunning.current) await loadMoney();
      if (wasRunning.current && !running) {
        const lr = t.run.last_run;
        setNotice(
          lr?.outcome === "error"
            ? { tone: "warn", text: `The run on ticket #${lr.ticket} stopped: ${lr.error ?? "unknown error"}` }
            : { tone: "ok", text: `The team finished ticket #${lr?.ticket}.` },
        );
      }
      wasRunning.current = running;
      return running;
    } catch (err) {
      if (err instanceof OfflineError) setOffline(true);
      else setLoadError(plainError(err));
      return false;
    } finally {
      setLoading(false);
    }
  }, [loadEvents, loadMoney]);

  // The polling loop: fast while a run goes, slow when idle, patient when offline.
  useEffect(() => {
    let timer: number | undefined;
    let alive = true;
    const loop = async () => {
      const running = await poll();
      if (!alive) return;
      const delay = running ? POLL_RUNNING_MS : offlineRef.current ? POLL_OFFLINE_MS : POLL_IDLE_MS;
      timer = window.setTimeout(loop, delay);
    };
    loop();
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [poll]);

  // Switching tickets shows that ticket's latest run right away.
  useEffect(() => {
    setEvents([]);
    setEventsRunId(null);
    setShowOldRun(false);
    loadEvents(selected).catch(() => undefined);
  }, [selected, loadEvents]);

  const locked = run.running || starting;
  const ticket = tickets.find((t) => t.id === selected) ?? null;
  const runningHere = run.running && run.last_run?.ticket === selected;
  // The audit trail keeps every run, even from before a reset. A run counts as this ticket's
  // current work only if the ticket has a decision now, or it is the run the backend just did.
  const oldRun =
    !!eventsRunId && !runningHere && !!ticket && !ticket.has_decision && run.last_run?.run_id !== eventsRunId;
  // While a run goes, show only that run's events (the trail may still hold an older run).
  const liveRunId = runningHere ? run.last_run?.run_id ?? null : null;
  const eventsAsc = useMemo(() => {
    if (liveRunId) return [...events].reverse().filter((e) => e.run_id === liveRunId);
    return oldRun && !showOldRun ? [] : [...events].reverse();
  }, [events, oldRun, showOldRun, liveRunId]);
  const desk = useMemo(() => deriveDesk(eventsAsc, runningHere), [eventsAsc, runningHere]);
  const summary = useMemo(() => summarize(eventsAsc), [eventsAsc]);

  // The Boss's final call, as plain text (the backend sends it as JSON).
  const bossReply = useMemo(() => {
    const lr = run.last_run;
    if (oldRun && !showOldRun) return null;
    if (lr?.reply && lr.ticket === selected && lr.run_id === eventsRunId) return lr.reply;
    const last = eventsAsc.filter((e) => e.agent === "boss" && e.depth === 0 && e.type === "answer").pop();
    return last ? parseReply(last.said) : null;
  }, [run.last_run, selected, eventsRunId, eventsAsc, oldRun, showOldRun]);
  const decision = runningHere ? null : bossReply?.answer ?? null;

  const startRun = async () => {
    if (!ticket) return;
    setStarting(true);
    setNotice(null);
    try {
      const r = await api.runTicket(ticket.id);
      setNotice({ tone: "ok", text: `The team is on ticket #${r.ticket}. A run takes 3 to 4 minutes.` });
      wasRunning.current = false;
      await poll();
    } catch (err) {
      setNotice({ tone: "warn", text: plainError(err) });
    } finally {
      setStarting(false);
    }
  };

  const approve = async (r: PayRequest) => {
    setNotice(null);
    try {
      const res = await api.approve(r.request_id, ME);
      setNotice({
        tone: "ok",
        text: `Approved ${res.request_id}: paid ${money(res.amount)}${r.payee ? ` to ${r.payee}` : ""}. Cash ${money(res.balance_before)} → ${money(res.balance_after)}.`,
      });
    } catch (err) {
      setNotice({ tone: "warn", text: `Not approved: ${plainError(err)}` });
    }
    await poll();
  };

  const decline = async (r: PayRequest, reason: string) => {
    setNotice(null);
    try {
      const res = await api.decline(r.request_id, ME, reason);
      setNotice({ tone: "ok", text: `Declined ${res.request_id}. No cash moved.` });
    } catch (err) {
      setNotice({ tone: "warn", text: `Not declined: ${plainError(err)}` });
    }
    await poll();
  };

  const reset = async () => {
    setNotice(null);
    try {
      await api.reset();
      setNotice({ tone: "ok", text: "The desk is reset. The activity log is kept." });
    } catch (err) {
      setNotice({ tone: "warn", text: `Not reset: ${plainError(err)}` });
    }
    await poll();
  };

  let action: { label: string; disabled: boolean; hint?: string } | null = null;
  if (ticket && ticket.status !== "resolved") {
    if (run.running) action = { label: runningHere ? "The team is working…" : "Another run is going", disabled: true };
    else if (ticket.pending_requests > 0) action = { label: "Waiting for you", disabled: true, hint: "Approve or decline the slips below first." };
    else if (ticket.has_decision) action = { label: "Continue", disabled: locked };
    else action = { label: "Start the team", disabled: locked };
  }

  const runLabel = eventsRunId
    ? `${runningHere ? "live now" : "latest run"}${run.last_run?.run_id === eventsRunId && run.last_run.started_at ? `, started ${timeAgo(run.last_run.started_at)}` : ""}`
    : null;

  return (
    <div className="page">
      <header className="masthead">
        <div>
          <p className="eyebrow">Campus Customs</p>
          <h1 className="title">The desk</h1>
          <p className="subtitle">Five colleagues, three tickets. Nothing is paid until you sign.</p>
        </div>
        <Cash cash={cash} loading={loading} />
      </header>

      <p className="sr-only" aria-live="polite">
        {run.running ? `The team is working on ticket ${run.last_run?.ticket}.` : ""}
      </p>

      {offline && (
        <div className="banner banner--offline" role="alert">
          <strong>The backend is not running.</strong> Start it from <code>backend/</code> with{" "}
          <code>..\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000</code>. The board will reconnect
          to {API_URL} on its own.
        </div>
      )}
      {loadError && !offline && (
        <div className="banner banner--warn" role="alert">
          {loadError} <button type="button" className="btn btn--tiny" onClick={() => poll()}>Try again</button>
        </div>
      )}
      {notice && (
        <div className={`banner banner--${notice.tone}`} role="status">
          {notice.text}
          <button type="button" className="banner-close" aria-label="Dismiss" onClick={() => setNotice(null)}>×</button>
        </div>
      )}

      {loading && tickets.length === 0 && !offline ? (
        <p className="loading">Setting out the chairs…</p>
      ) : (
        <main className="layout">
          <Tickets tickets={tickets} selected={selected} runningTicket={run.running ? run.last_run?.ticket ?? null : null} onSelect={setSelected} />

          <div className="workspace">
            {ticket ? (
              <section className="ticket-head" aria-labelledby="ticket-title">
                <div>
                  <p className="eyebrow">{TICKET_TYPE_LABEL[ticket.type] ?? ticket.type} · #{ticket.id}</p>
                  <h2 id="ticket-title" className="ticket-title">{ticket.subject}</h2>
                  {ticket.status === "resolved" ? (
                    <p className="stamp stamp--big">Resolved</p>
                  ) : (
                    ticket.open_because.length > 0 && <p className="waiting-line">Waiting for: {ticket.open_because.join("; ")}</p>
                  )}
                </div>
                {action && (
                  <div className="ticket-action">
                    <button type="button" className="btn btn--primary btn--large" disabled={action.disabled} onClick={startRun}>
                      {starting ? "Starting…" : action.label}
                    </button>
                    {action.hint && <p className="muted small">{action.hint}</p>}
                  </div>
                )}
              </section>
            ) : (
              !offline && <p className="muted">Pick a ticket on the left.</p>
            )}

            {ticket && (
              <section className={`desk${runningHere ? " desk--live" : ""}`} aria-label="The team">
                <Seat agent="boss" seat={desk.seats.boss} wide decision={decision} />
                {bossReply?.human_action && !runningHere && (
                  <p className="next-for-you"><span>Next for you</span>{bossReply.human_action}</p>
                )}
                <div className="seats">
                  {SEAT_ORDER.map((a) => (
                    <Seat key={a} agent={a} seat={desk.seats[a]} />
                  ))}
                </div>
                {(!eventsRunId || (oldRun && !showOldRun)) && !runningHere && (
                  <p className="muted center">
                    The team has not worked this ticket since the desk was reset.{" "}
                    {action && !action.disabled ? `Press “${action.label}”.` : ""}
                    {oldRun && (
                      <>
                        {" "}
                        <button type="button" className="link" onClick={() => setShowOldRun(true)}>
                          Show the run from before the reset
                        </button>
                      </>
                    )}
                  </p>
                )}
                {oldRun && showOldRun && (
                  <p className="muted center small">
                    This run happened before the last reset, so its notes and payments are gone.{" "}
                    <button type="button" className="link" onClick={() => setShowOldRun(false)}>Hide it</button>
                  </p>
                )}
              </section>
            )}

            <Slips requests={requests} balance={cash?.balance ?? null} locked={locked} onApprove={approve} onDecline={decline} />

            {ticket && <Summary items={summary} runLabel={oldRun ? (showOldRun ? "before the last reset" : null) : runLabel} />}
          </div>
        </main>
      )}

      <footer className="footer">
        <span className="muted small">
          {Object.values(AGENTS).map((a) => a.title).join(" · ")} · backend {API_URL}
        </span>
        <ResetDesk locked={locked || offline} onReset={reset} />
      </footer>
    </div>
  );
}
