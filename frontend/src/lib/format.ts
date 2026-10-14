import { useEffect, useRef, useState } from "react";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2, minimumFractionDigits: 0 });
export const money = (n: number | null | undefined): string => (n === null || n === undefined ? "—" : usd.format(n));

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Counts smoothly from the old value to the new one (or jumps, if the user prefers less motion). */
export function useAnimatedNumber(target: number | null, durationMs = 1400): number | null {
  const [shown, setShown] = useState<number | null>(target);
  const from = useRef<number | null>(target);
  useEffect(() => {
    if (target === null) return;
    const start = from.current;
    from.current = target;
    // Jump instead of animating if motion is reduced or the page is hidden (no frames are drawn then).
    if (start === null || start === target || prefersReducedMotion() || document.hidden) {
      setShown(target);
      return;
    }
    let raf = 0;
    const t0 = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - t0) / durationMs);
      const eased = 1 - Math.pow(1 - t, 3);
      setShown(start + (target - start) * eased);
      if (t < 1 && !document.hidden) raf = requestAnimationFrame(step);
      else setShown(target);
    };
    raf = requestAnimationFrame(step);
    // Safety net: if the window is covered and draws no frames, still land on the real number.
    const settle = window.setTimeout(() => setShown(target), durationMs + 250);
    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(settle);
    };
  }, [target, durationMs]);
  return shown;
}

export const timeAgo = (iso: string | undefined): string => {
  if (!iso) return "";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  return m < 60 ? `${m} min ago` : `${Math.round(m / 60)} h ago`;
};
