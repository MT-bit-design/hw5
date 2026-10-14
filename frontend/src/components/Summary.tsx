import type { CSSProperties } from "react";
import { AGENTS } from "../lib/agents";
import type { AgentSummary } from "../lib/events";

export function Summary({ items, runLabel }: { items: AgentSummary[]; runLabel: string | null }) {
  return (
    <section className="summary" aria-labelledby="summary-title">
      <h2 id="summary-title" className="section-title">
        What each colleague did {runLabel && <span className="muted small">· {runLabel}</span>}
      </h2>
      {items.length === 0 ? (
        <p className="muted">No one has worked this ticket yet.</p>
      ) : (
        <ul className="summary-list">
          {items.map((s) => {
            const meta = AGENTS[s.agent];
            return (
              <li key={s.agent} className="summary-item" style={{ "--accent": meta.accent } as CSSProperties}>
                <span className="summary-dot" aria-hidden="true" />
                <div>
                  <p className="summary-who">{meta.title}</p>
                  <p className="summary-what">{s.sentence}</p>
                  {s.answer && <p className="summary-said">“{s.answer}”</p>}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
