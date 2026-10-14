import type { Ticket } from "../types";
import { TICKET_TYPE_LABEL } from "../lib/agents";

interface Props {
  tickets: Ticket[];
  selected: number | null;
  runningTicket: number | null;
  onSelect: (id: number) => void;
}

function TicketCard({ t, selected, running, onSelect }: { t: Ticket; selected: boolean; running: boolean; onSelect: () => void }) {
  const resolved = t.status === "resolved";
  return (
    <button
      type="button"
      className={`ticket${selected ? " ticket--selected" : ""}${resolved ? " ticket--resolved" : ""}`}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className="ticket-top">
        <span className="ticket-id">#{t.id}</span>
        <span className="ticket-type">{TICKET_TYPE_LABEL[t.type] ?? t.type}</span>
        {running && <span className="pill pill--live">Team at work</span>}
        {!running && !resolved && t.pending_requests > 0 && <span className="pill pill--you">Waiting for you</span>}
      </span>
      <span className="ticket-subject">{t.subject}</span>
      {t.sku && (
        <span className="ticket-detail">
          {t.qty} × {t.sku} · size {t.size}
        </span>
      )}
      {resolved ? (
        <span className="stamp" aria-label="Resolved">Resolved</span>
      ) : (
        t.open_because.length > 0 && <span className="ticket-waiting">Waiting for: {t.open_because.join("; ")}</span>
      )}
    </button>
  );
}

export function Tickets({ tickets, selected, runningTicket, onSelect }: Props) {
  const open = tickets.filter((t) => t.status !== "resolved");
  const done = tickets.filter((t) => t.status === "resolved");
  return (
    <nav className="tickets" aria-label="Tickets">
      <h2 className="eyebrow">On the desk</h2>
      {open.length === 0 && <p className="muted small">Nothing open. Every ticket is resolved.</p>}
      <ul className="ticket-list">
        {open.map((t) => (
          <li key={t.id}>
            <TicketCard t={t} selected={selected === t.id} running={runningTicket === t.id} onSelect={() => onSelect(t.id)} />
          </li>
        ))}
      </ul>
      {done.length > 0 && (
        <>
          <h2 className="eyebrow eyebrow--done">Done</h2>
          <ul className="ticket-list ticket-list--done">
            {done.map((t) => (
              <li key={t.id}>
                <TicketCard t={t} selected={selected === t.id} running={false} onSelect={() => onSelect(t.id)} />
              </li>
            ))}
          </ul>
        </>
      )}
    </nav>
  );
}
