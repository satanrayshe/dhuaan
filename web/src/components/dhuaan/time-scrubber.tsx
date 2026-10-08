"use client";

import { useEffect, useMemo } from "react";
import { PauseIcon, PlayIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useI18n } from "@/lib/i18n";
import { playback, useHour, usePlaying, useSpeed, type Speed } from "@/lib/playback";
import { H_MAX, H_MIN, HOUR_MS, istDayTime, istHourOf, isNightIst, mixingDepth, toMs } from "@/lib/time";
import { cn } from "@/lib/utils";

const SPAN = H_MAX - H_MIN;

export function TimeScrubber({ t0, className }: { t0: string; className?: string }) {
  const { t, lang } = useI18n();
  const hour = useHour();
  const playing = usePlaying();
  const speed = useSpeed();
  const t0ms = toMs(t0);

  // space toggles play when not typing
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (e.code !== "Space" || el.closest("input,textarea,button,[role=slider],[role=dialog]")) return;
      e.preventDefault();
      playback.toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const hours = useMemo(() => Array.from({ length: SPAN + 1 }, (_, i) => i + H_MIN), []);
  const midnights = useMemo(() => hours.filter((h) => istHourOf(t0ms + h * HOUR_MS) < 1), [hours, t0ms]);
  const pct = (h: number) => ((h - H_MIN) / SPAN) * 100;
  const label = istDayTime(t0ms + hour * HOUR_MS, lang);
  const rel = hour === 0 ? t("scrub.now") : `${hour > 0 ? "+" : ""}${hour} h`;

  return (
    <div className={cn("rounded-lg border border-panel-border bg-panel px-3 pt-2.5 pb-2 shadow-[0_1px_2px_rgb(0_0_0/0.04),0_8px_24px_-12px_rgb(0_0_0/0.18)] backdrop-blur-md", className)}>
      <div className="flex items-center gap-2 sm:gap-3">
        <Button
          size="icon"
          className="size-9 shrink-0"
          data-coach="play"
          onClick={() => playback.toggle()}
          aria-label={playing ? t("scrub.pause") : t("scrub.play")}
          aria-pressed={playing}
        >
          {playing ? <PauseIcon aria-hidden /> : <PlayIcon aria-hidden />}
        </Button>
        <div className="min-w-0" aria-live="off">
          <p className="truncate text-sm leading-tight font-medium">{label} IST</p>
          <p className="font-mono text-[0.7rem] leading-tight text-muted-foreground">
            {rel} · {hour < 0 ? t("scrub.past") : t("scrub.future")}
          </p>
        </div>
        {hour !== 0 && (
          <Button variant="outline" size="sm" className="shrink-0" onClick={() => playback.setHour(0)}>
            {t("scrub.now")}
          </Button>
        )}
        <ToggleGroup
          type="single"
          size="sm"
          variant="outline"
          spacing={0}
          value={String(speed)}
          onValueChange={(v) => v && playback.setSpeed(Number(v) as Speed)}
          aria-label={t("scrub.speed")}
          className="ml-auto shrink-0"
        >
          {[1, 4, 16].map((s) => (
            <ToggleGroupItem key={s} value={String(s)} className="h-7 min-w-9 px-1.5 font-mono text-xs">
              {s}×
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      <div className="relative mt-3 px-1.5">
        {/* day ticks */}
        <div className="relative h-4 text-[0.66rem] text-muted-foreground" aria-hidden>
          {midnights.map((h) => (
            <span key={h} className="absolute -translate-x-1/2 font-mono" style={{ left: `${pct(h)}%` }}>
              {istDayTime(t0ms + h * HOUR_MS, lang).split(" ")[0]}
            </span>
          ))}
        </div>
        <div className="relative">
          <span className="absolute top-1/2 h-3 w-px -translate-y-1/2 bg-foreground/60" style={{ left: `${pct(0)}%` }} aria-hidden />
          <Slider
            min={H_MIN}
            max={H_MAX}
            step={1}
            value={[hour]}
            onValueChange={([v]) => {
              if (playback.get().playing) playback.pause();
              playback.setHour(v);
            }}
            aria-label={t("scrub.time")}
            aria-valuetext={`${label} IST, ${rel}`}
            className="py-2"
          />
        </div>
        {/* boundary-layer band: why nights are worse */}
        <div data-coach="blh" className="mt-1">
          <svg viewBox={`0 0 ${SPAN + 1} 12`} preserveAspectRatio="none" className="block h-5 w-full" role="img" aria-label={`${t("scrub.mixing")}: ${t("scrub.trapped")}; ${t("scrub.mixed")}`}>
            {hours.map((h, i) => {
              const ms = t0ms + h * HOUR_MS;
              const d = mixingDepth(ms);
              return (
                <g key={h}>
                  {isNightIst(ms) && <rect x={i} y={0} width={1.02} height={12} fill="var(--night)" />}
                  <rect x={i + 0.1} y={12 - d * 11} width={0.8} height={d * 11} fill="var(--muted-foreground)" opacity={0.35} />
                </g>
              );
            })}
            <rect x={hour - H_MIN} y={0} width={1} height={12} fill="var(--foreground)" opacity={0.5} />
          </svg>
          <div className="mt-1 flex flex-wrap items-center justify-between gap-x-3 text-[0.66rem] text-muted-foreground">
            <span>
              {t("scrub.mixing")} <span className="opacity-70">({t("scrub.climo")})</span>
            </span>
            <span className="flex items-center gap-3">
              <span className="inline-flex items-center gap-1">
                <span className="inline-block size-2 rounded-[1px] bg-[var(--night)] ring-1 ring-border" aria-hidden /> {t("scrub.trapped")}
              </span>
              <span className="hidden items-center gap-1 sm:inline-flex">
                <span className="inline-block h-2 w-1 rounded-[1px] bg-muted-foreground/40" aria-hidden /> {t("scrub.mixed")}
              </span>
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
