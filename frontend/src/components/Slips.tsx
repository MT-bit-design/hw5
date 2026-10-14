import { useState } from "react";
import type { PayRequest } from "../types";
import { money } from "../lib/format";

interface Props {
  requests: PayRequest[];
  balance: number | null;
  locked: boolean;
  onApprove: (r: PayRequest) => Promise<void>;
  onDecline: (r: PayRequest, reason: string) => Promise<void>;
}

const KIND_WORDS: Record<string, string> = { invoice: "Vendor invoice", rent: "Rent", purchase_order: "Restock order" };

function Slip({ r, balance, locked, onApprove, onDecline }: { r: PayRequest } & Omit<Props, "requests">) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState<"approve" | "decline" | null>(null);
  const after = balance !== null && r.amount !== null ? balance - r.amount : null;
  const what =
    r.kind === "purchase_order"
      ? `${r.qty} × ${r.sku} size ${r.size}`
      : r.kind === "invoice" ? `Invoice ${r.ref_id}` : `Lease ${r.ref_id}`;
  const run = async (which: "approve" | "decline") => {
    setBusy(which);
    try {
      await (which === "approve" ? onApprove(r) : onDecline(r, reason.trim()));
    } finally {
      setBusy(null);
    }
  };
  const disabled = locked || busy !== null;
  return (
    <article className="slip" aria-labelledby={`slip-${r.request_id}`}>
      <header className="slip-head">
        <span className="pill pill--you">Waiting for you</span>
        <span className="slip-id" id={`slip-${r.request_id}`}>{r.request_id} · ticket #{r.ticket_id}</span>
      </header>
      <p className="slip-amount">{money(r.amount)}</p>
      <dl className="slip-facts">
        <dt>Pay to</dt><dd>{r.payee ?? "—"}</dd>
        <dt>For</dt><dd>{KIND_WORDS[r.kind] ?? r.kind} · {what}</dd>
        <dt>From</dt><dd>{r.account}</dd>
        <dt>Cash after</dt>
        <dd className={after !== null && after < 0 ? "bad" : undefined}>{money(after)}</dd>
        <dt>Asked by</dt><dd>{r.requested_by}, {r.requested_on}</dd>
      </dl>
      <div className="slip-sign">
        <label className="slip-reason">
          <span>Reason if you decline (optional)</span>
          <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={120} disabled={disabled} placeholder="e.g. not this month" />
        </label>
        <div className="slip-buttons">
          <button type="button" className="btn btn--primary" disabled={disabled} onClick={() => run("approve")}>
            {busy === "approve" ? "Approving…" : "Approve"}
          </button>
          <button type="button" className="btn btn--quiet" disabled={disabled} onClick={() => run("decline")}>
            {busy === "decline" ? "Declining…" : "Decline"}
          </button>
        </div>
        <p className="slip-line" aria-hidden="true">Signed, MT</p>
      </div>
    </article>
  );
}

export function Slips(props: Props) {
  return (
    <section className="slips" aria-labelledby="slips-title">
      <h2 id="slips-title" className="section-title">Waiting for your signature</h2>
      {props.requests.length === 0 ? (
        <p className="muted">No payments or orders are waiting. Agents can only ask; nothing is paid until you approve.</p>
      ) : (
        <div className="slip-row">
          {props.requests.map((r) => (
            <Slip key={r.request_id} r={r} {...props} />
          ))}
        </div>
      )}
    </section>
  );
}
