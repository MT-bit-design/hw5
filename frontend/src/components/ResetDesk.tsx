import { useEffect, useRef, useState } from "react";

interface Props {
  locked: boolean;
  onReset: () => Promise<void>;
}

/** Small and out of the way, with a clear confirm step. */
export function ResetDesk({ locked, onReset }: Props) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const yesRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (confirming) yesRef.current?.focus();
  }, [confirming]);

  if (!confirming) {
    return (
      <button type="button" className="btn btn--tiny" disabled={locked} onClick={() => setConfirming(true)}>
        Reset desk
      </button>
    );
  }
  return (
    <div className="reset-confirm" role="alertdialog" aria-labelledby="reset-q" onKeyDown={(e) => e.key === "Escape" && setConfirming(false)}>
      <p id="reset-q">Put tickets, cash and requests back to the start? The activity log is kept.</p>
      <button
        ref={yesRef}
        type="button"
        className="btn btn--tiny btn--danger"
        disabled={busy || locked}
        onClick={async () => {
          setBusy(true);
          try {
            await onReset();
          } finally {
            setBusy(false);
            setConfirming(false);
          }
        }}
      >
        {busy ? "Resetting…" : "Yes, reset"}
      </button>
      <button type="button" className="btn btn--tiny" onClick={() => setConfirming(false)}>
        Cancel
      </button>
    </div>
  );
}
