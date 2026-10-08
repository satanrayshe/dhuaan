"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Button } from "@/components/ui/button";
import { useI18n, type DictKey } from "@/lib/i18n";

const KEY = "dhuaan.coach.v1";
const STEPS: { target: string; title: DictKey; body: DictKey }[] = [
  { target: "play", title: "coach.1.title", body: "coach.1.body" },
  { target: "search", title: "coach.2.title", body: "coach.2.body" },
  { target: "blh", title: "coach.3.title", body: "coach.3.body" },
];

function visibleTarget(name: string): HTMLElement | null {
  const els = Array.from(document.querySelectorAll<HTMLElement>(`[data-coach="${name}"]`));
  return els.find((e) => e.offsetParent !== null && e.getBoundingClientRect().width > 0) ?? null;
}

/** First-run, three-step, non-modal coach marks for the map. */
export function CoachMarks({ ready }: { ready: boolean }) {
  const { t } = useI18n();
  const [step, setStep] = useState<number | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number; arrowLeft: number; below: boolean } | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ready) return;
    try {
      if (window.localStorage.getItem(KEY)) return;
    } catch {}
    const id = setTimeout(() => setStep(0), 900);
    return () => clearTimeout(id);
  }, [ready]);

  const finish = useCallback(() => {
    setStep(null);
    try {
      window.localStorage.setItem(KEY, "1");
    } catch {}
  }, []);

  const place = useCallback(() => {
    if (step === null) return;
    const el = visibleTarget(STEPS[step].target);
    if (!el) return setPos(null);
    const r = el.getBoundingClientRect();
    const w = Math.min(300, window.innerWidth - 24);
    const below = r.top < 220;
    const left = Math.max(12, Math.min(window.innerWidth - w - 12, r.left + r.width / 2 - w / 2));
    setPos({ top: below ? r.bottom + 12 : r.top - 12, left, arrowLeft: r.left + r.width / 2 - left, below });
  }, [step]);

  useLayoutEffect(() => {
    const raf = requestAnimationFrame(place);
    window.addEventListener("resize", place);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", place);
    };
  }, [place]);

  useEffect(() => {
    if (step !== null) cardRef.current?.focus();
  }, [step, pos]);

  if (step === null || !pos) return null;
  const s = STEPS[step];
  return createPortal(
    <div
      ref={cardRef}
      tabIndex={-1}
      role="dialog"
      aria-modal="false"
      aria-labelledby="coach-title"
      onKeyDown={(e) => e.key === "Escape" && finish()}
      className="fixed z-[60] w-[min(300px,calc(100vw-24px))] rounded-lg border border-border bg-popover p-4 text-popover-foreground shadow-[0_12px_40px_-12px_rgb(0_0_0/0.35)] outline-none animate-in fade-in-0 zoom-in-95"
      style={{ top: pos.top, left: pos.left, transform: pos.below ? undefined : "translateY(-100%)" }}
    >
      <span
        className="absolute size-3 rotate-45 border-border bg-popover"
        style={{
          left: Math.max(12, Math.min(276, pos.arrowLeft)) - 6,
          ...(pos.below ? { top: -6, borderTopWidth: 1, borderLeftWidth: 1 } : { bottom: -6, borderBottomWidth: 1, borderRightWidth: 1 }),
        }}
        aria-hidden
      />
      <p className="font-mono text-[0.68rem] text-muted-foreground">
        {step + 1} / {STEPS.length}
      </p>
      <p id="coach-title" className="mt-1 text-sm font-semibold">
        {t(s.title)}
      </p>
      <p className="mt-1 text-sm text-muted-foreground">{t(s.body)}</p>
      <div className="mt-3 flex items-center justify-between">
        <Button variant="ghost" size="sm" onClick={finish}>
          {t("coach.skip")}
        </Button>
        <Button size="sm" onClick={() => (step + 1 < STEPS.length ? setStep(step + 1) : finish())}>
          {step + 1 < STEPS.length ? t("coach.next") : t("coach.done")}
        </Button>
      </div>
    </div>,
    document.body,
  );
}
