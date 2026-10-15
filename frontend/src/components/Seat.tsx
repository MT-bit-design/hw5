import type { CSSProperties } from "react";
import type { AgentName } from "../types";
import { AGENTS } from "../lib/agents";
import type { Seat as SeatData } from "../lib/events";

interface Props {
  agent: AgentName;
  seat: SeatData;
  wide?: boolean;
  /** For the Boss: the final call, in plain words. */
  decision?: string | null;
  /** When the decision comes from an earlier run, say so (and still show this run's line). */
  decisionFrom?: string | null;
}

const STATE_WORDS: Record<SeatData["state"], string> = {
  idle: "At the desk",
  active: "Working",
  waiting: "Waiting on a colleague",
  done: "Done",
};

export function Seat({ agent, seat, wide = false, decision, decisionFrom }: Props) {
  const meta = AGENTS[agent];
  const style = { "--accent": meta.accent, "--tint": meta.tint } as CSSProperties;
  const chips = seat.chips.slice(-6);
  return (
    <article
      className={`seat seat--${seat.state}${wide ? " seat--wide" : ""}`}
      style={style}
      aria-label={`${meta.title}: ${STATE_WORDS[seat.state]}`}
      aria-current={seat.state === "active" ? "true" : undefined}
    >
      <header className="seat-head">
        <span className="seat-avatar" aria-hidden="true">{meta.initial}</span>
        <div>
          <h3 className="seat-name">{meta.title}</h3>
          <p className="seat-voice">{meta.voice}</p>
        </div>
        <span className="seat-state">{STATE_WORDS[seat.state]}</span>
      </header>

      {seat.note && (
        <p className="seat-note" key={seat.note.key}>
          <span className="seat-note-from">Note from {AGENTS[seat.note.from].title}</span>
          {seat.note.text}
        </p>
      )}

      {wide && decision && decisionFrom && seat.line && <p className="seat-line seat-line--stopped">{seat.line}</p>}
      {wide && decision ? (
        <>
          {decisionFrom && <p className="seat-decision-from">{decisionFrom}</p>}
          <blockquote className="seat-decision">{decision}</blockquote>
        </>
      ) : (
        <p className={`seat-line${seat.line ? "" : " muted"}`}>{seat.line ?? "Nothing yet on this ticket."}</p>
      )}

      {chips.length > 0 && (
        <ul className="chips" aria-label={`${meta.title}'s tool calls`}>
          {chips.map((c) => (
            <li key={c.key} className={`chip${c.refused ? " chip--refused" : ""}`} title={c.refused ? `Refused: ${c.refused}` : c.tool}>
              {c.label}
              {c.requestId ? ` · ${c.requestId}` : ""}
              {c.refused ? " · refused" : ""}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
