import { useEffect, useRef, useState } from "react";
import type { CashResponse } from "../types";
import { money, useAnimatedNumber } from "../lib/format";

interface Props {
  cash: CashResponse | null;
  loading: boolean;
}

/** One big calm number. When it drops, it counts down and leaves a small "was" trail. */
export function Cash({ cash, loading }: Props) {
  const balance = cash?.balance ?? null;
  const shown = useAnimatedNumber(balance);
  const prev = useRef<number | null>(balance);
  const [was, setWas] = useState<number | null>(null);

  useEffect(() => {
    if (balance === null) return;
    if (prev.current !== null && balance !== prev.current) setWas(prev.current);
    prev.current = balance;
  }, [balance]);

  return (
    <section className="cash" aria-labelledby="cash-label">
      <p id="cash-label" className="eyebrow">Checking</p>
      <p className="cash-number" aria-live="polite">
        {loading && balance === null ? <span className="muted">…</span> : money(shown)}
      </p>
      {was !== null && balance !== null && was !== balance ? (
        <p className="cash-was">
          was <s>{money(was)}</s> · {balance < was ? `${money(was - balance)} paid out` : `${money(balance - was)} back after reset`}
        </p>
      ) : (
        <p className="cash-was muted">{cash ? `as of the shop day ${cash.as_of}` : " "}</p>
      )}
    </section>
  );
}
