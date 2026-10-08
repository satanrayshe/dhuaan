"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/skeleton";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { BACKTEST_COLORS } from "@/lib/colors";
import { artifactUrl, revalidate, useBacktest } from "@/lib/data";
import { useI18n } from "@/lib/i18n";
import type { BacktestMetrics, ExploratoryRegional, Lang } from "@/lib/types";
import { cn } from "@/lib/utils";
import { useThemeName } from "./bits";

// Recharts loads after the metrics and method text are on screen
const StationChart = dynamic(() => import("./backtest-chart").then((m) => m.StationChart), {
  ssr: false,
  loading: () => <div className="h-60 animate-pulse rounded-lg border border-border bg-muted/30" />,
});

const METRIC_LABELS: Record<string, { label: string; fmt: (v: number) => string; better: "up" | "down" }> = {
  hit_rate: { label: "Hit rate (smoke episodes)", fmt: (v) => `${Math.round(v * 100)}%`, better: "up" },
  false_alarm_ratio: { label: "False-alarm ratio", fmt: (v) => `${Math.round(v * 100)}%`, better: "down" },
  median_lead_h: { label: "Median lead time", fmt: (v) => `${v.toFixed(0)} h`, better: "up" },
  pearson_r: { label: "Pearson r, hourly excess", fmt: (v) => v.toFixed(2), better: "up" },
  r2: { label: "R² after calibration", fmt: (v) => v.toFixed(2), better: "up" },
};

const METHOD: Record<Lang, string[]> = {
  en: [
    "A season replay around the 11 Nov 2025 smoke episode (window shown above). Definitions were fixed before looking at the data.",
    "Observed smoke signal: PM2.5 minus a rolling 7-day 10th-percentile baseline at the same station.",
    "Calibration: least squares PM2.5 excess ≈ α × model smoke, fitted on the first part of the window; skill is scored on the held-out remainder only.",
    "An episode is an excess of at least 60 µg/m³ for 3 or more hours; a hit is a forecast crossing within ±6 h.",
    "A uses VIIRS/MODIS detections only, as official counts do. B adds hourly afternoon geostationary detections. The A-to-B difference is the measured cost of the afternoon gap.",
  ],
  hi: [
    "11 नवंबर 2025 की धुआँ घटना के आसपास सीज़न का दोहराव (अवधि ऊपर दी गई है)। परिभाषाएँ डेटा देखने से पहले तय की गईं।",
    "देखा गया धुआँ संकेत: PM2.5 में से उसी स्टेशन की 7-दिन की 10वीं प्रतिशतक आधार रेखा घटाकर।",
    "अंशांकन: अवधि के पहले हिस्से पर न्यूनतम वर्ग; कौशल केवल बाकी, अलग रखे गए हिस्से पर मापा गया।",
    "घटना: कम से कम 3 घंटे तक 60 µg/m³ या अधिक अतिरिक्त; सफलता: ±6 घंटे में पूर्वानुमान का पार होना।",
    "A में केवल VIIRS/MODIS, B में दोपहर बाद के भूस्थिर उपग्रह भी। A और B का अंतर दोपहर बाद की कमी की मापी गई कीमत है।",
  ],
  pa: [
    "11 ਨਵੰਬਰ 2025 ਦੀ ਧੂੰਆਂ ਘਟਨਾ ਦੇ ਆਲੇ-ਦੁਆਲੇ ਸੀਜ਼ਨ ਦਾ ਦੁਹਰਾਅ (ਮਿਆਦ ਉੱਪਰ ਦਿੱਤੀ ਹੈ)। ਪਰਿਭਾਸ਼ਾਵਾਂ ਡਾਟਾ ਵੇਖਣ ਤੋਂ ਪਹਿਲਾਂ ਤੈਅ ਕੀਤੀਆਂ।",
    "ਵੇਖਿਆ ਧੂੰਆਂ ਸੰਕੇਤ: PM2.5 ਵਿੱਚੋਂ ਉਸੇ ਸਟੇਸ਼ਨ ਦੀ 7-ਦਿਨ 10ਵੀਂ ਪ੍ਰਤੀਸ਼ਤਕ ਆਧਾਰ ਰੇਖਾ ਘਟਾ ਕੇ।",
    "ਕੈਲੀਬ੍ਰੇਸ਼ਨ: ਮਿਆਦ ਦੇ ਪਹਿਲੇ ਹਿੱਸੇ 'ਤੇ ਘੱਟੋ-ਘੱਟ ਵਰਗ; ਹੁਨਰ ਸਿਰਫ਼ ਬਾਕੀ, ਵੱਖਰੇ ਰੱਖੇ ਹਿੱਸੇ 'ਤੇ ਮਾਪਿਆ।",
    "ਘਟਨਾ: ਘੱਟੋ-ਘੱਟ 3 ਘੰਟੇ 60 µg/m³ ਜਾਂ ਵੱਧ ਵਾਧੂ; ਸਫਲਤਾ: ±6 ਘੰਟਿਆਂ ਵਿੱਚ ਭਵਿੱਖਬਾਣੀ ਦਾ ਪਾਰ ਹੋਣਾ।",
    "A ਵਿੱਚ ਸਿਰਫ਼ VIIRS/MODIS, B ਵਿੱਚ ਦੁਪਹਿਰ ਬਾਅਦ ਦੇ ਭੂ-ਸਥਿਰ ਉਪਗ੍ਰਹਿ ਵੀ। A ਅਤੇ B ਦਾ ਫ਼ਰਕ ਦੁਪਹਿਰ ਬਾਅਦ ਦੀ ਕਮੀ ਦੀ ਮਾਪੀ ਕੀਮਤ ਹੈ।",
  ],
};

const LIMITS: Record<Lang, string[]> = {
  en: [
    "Smoke from farm fires is one part of PM2.5. Traffic, industry, dust and winter inversions are not modelled; the excess baseline only partly removes them.",
    "If reanalysis weather was used instead of archived forecasts, skill here is better than a live forecast would achieve.",
    "Fires hidden by cloud or too small for the satellites are invisible to the model.",
    "Monitors are sparse in rural Punjab, where the smoke lands first, so village-level forecasts are not directly verified.",
    "Some stations fail. They are shown here, not dropped.",
  ],
  hi: [
    "खेतों की आग का धुआँ PM2.5 का एक हिस्सा है। यातायात, उद्योग, धूल और सर्दी की उलटी परतें मॉडल में नहीं हैं।",
    "अगर पूर्वानुमान की जगह पुनर्विश्लेषण मौसम लिया गया, तो यहाँ का कौशल असली पूर्वानुमान से बेहतर दिखता है।",
    "बादलों में छिपी या बहुत छोटी आग मॉडल को नहीं दिखती।",
    "ग्रामीण पंजाब में मॉनिटर कम हैं, जहाँ धुआँ पहले पहुँचता है, इसलिए गाँव स्तर के पूर्वानुमान सीधे सत्यापित नहीं हैं।",
    "कुछ स्टेशनों पर मॉडल विफल होता है। वे यहाँ दिखाए गए हैं, हटाए नहीं गए।",
  ],
  pa: [
    "ਖੇਤਾਂ ਦੀ ਅੱਗ ਦਾ ਧੂੰਆਂ PM2.5 ਦਾ ਇੱਕ ਹਿੱਸਾ ਹੈ। ਆਵਾਜਾਈ, ਉਦਯੋਗ, ਧੂੜ ਅਤੇ ਸਰਦੀ ਦੀਆਂ ਉਲਟ ਪਰਤਾਂ ਮਾਡਲ ਵਿੱਚ ਨਹੀਂ ਹਨ।",
    "ਜੇ ਭਵਿੱਖਬਾਣੀ ਦੀ ਥਾਂ ਮੁੜ-ਵਿਸ਼ਲੇਸ਼ਣ ਮੌਸਮ ਵਰਤਿਆ ਗਿਆ, ਤਾਂ ਇੱਥੇ ਦਾ ਹੁਨਰ ਅਸਲ ਭਵਿੱਖਬਾਣੀ ਨਾਲੋਂ ਵਧੀਆ ਦਿਸਦਾ ਹੈ।",
    "ਬੱਦਲਾਂ ਹੇਠ ਲੁਕੀਆਂ ਜਾਂ ਬਹੁਤ ਛੋਟੀਆਂ ਅੱਗਾਂ ਮਾਡਲ ਨੂੰ ਨਹੀਂ ਦਿਸਦੀਆਂ।",
    "ਪੇਂਡੂ ਪੰਜਾਬ ਵਿੱਚ ਮਾਨੀਟਰ ਘੱਟ ਹਨ, ਜਿੱਥੇ ਧੂੰਆਂ ਪਹਿਲਾਂ ਪਹੁੰਚਦਾ ਹੈ, ਇਸ ਲਈ ਪਿੰਡ ਪੱਧਰ ਦੀਆਂ ਭਵਿੱਖਬਾਣੀਆਂ ਸਿੱਧੀਆਂ ਪ੍ਰਮਾਣਿਤ ਨਹੀਂ ਹਨ।",
    "ਕੁਝ ਸਟੇਸ਼ਨਾਂ 'ਤੇ ਮਾਡਲ ਫੇਲ੍ਹ ਹੁੰਦਾ ਹੈ। ਉਹ ਇੱਥੇ ਦਿਖਾਏ ਗਏ ਹਨ, ਹਟਾਏ ਨਹੀਂ।",
  ],
};

/** raw counts are shown inside the hit-rate tile, never as tiles of their own */
const COUNT_KEYS = new Set([
  "n_episodes", "n_hits", "episodes", "hits", "n_false_alarms", "n_forecast_episodes", "n_lead_episodes", "n_stations", "n_hours",
  "share_hours_obs_ge60", "share_hours_pred_ge60",
]);

type MetricPair = { A?: BacktestMetrics; B?: BacktestMetrics };

function metricKeysOf(metrics: MetricPair): string[] {
  const keys = new Set([...Object.keys(metrics.A ?? {}), ...Object.keys(metrics.B ?? {})]);
  // a metric undefined for both configurations (e.g. FAR with 0 forecast episodes) gets no tile
  const numeric = [...keys].filter((k) => typeof (metrics.A?.[k] ?? metrics.B?.[k]) === "number");
  const known = Object.keys(METRIC_LABELS).filter((k) => numeric.includes(k));
  const other = numeric.filter((k) => !(k in METRIC_LABELS) && !COUNT_KEYS.has(k) && !k.startsWith("n_") && !k.startsWith("_"));
  return [...known, ...other];
}

const cnt = (m: BacktestMetrics | undefined, k: string) => String(m?.[k] ?? "-");

function MetricTiles({ metrics, compact = false }: { metrics: MetricPair; compact?: boolean }) {
  const { t } = useI18n();
  const keys = metricKeysOf(metrics);
  return (
    <div
      className={cn(
        "mt-3 grid gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-2",
        keys.length >= 5 ? "lg:grid-cols-5" : keys.length === 3 ? "lg:grid-cols-3" : "lg:grid-cols-4",
      )}
    >
      {keys.map((k) => {
        const m = METRIC_LABELS[k] ?? { label: k.replace(/_/g, " "), fmt: (v: number) => String(+v.toFixed(2)), better: "up" as const };
        const a = metrics.A?.[k] as number | undefined;
        const b = metrics.B?.[k] as number | undefined;
        const improved = a != null && b != null && (m.better === "up" ? b > a : b < a);
        return (
          <div key={k} className={cn("bg-background", compact ? "p-3" : "p-4")}>
            <p className="text-xs text-muted-foreground">{m.label}</p>
            <div className="mt-2 flex items-baseline gap-4">
              <div>
                <p className="font-mono text-[0.68rem] text-muted-foreground">A</p>
                <p className={cn("font-semibold tracking-tight", compact ? "text-lg" : "text-xl")}>{a != null ? m.fmt(a) : "-"}</p>
              </div>
              <div>
                <p className="font-mono text-[0.68rem] text-muted-foreground">B</p>
                <p className={cn("font-semibold tracking-tight", compact ? "text-lg" : "text-xl")}>{b != null ? m.fmt(b) : "-"}</p>
              </div>
              {a != null && b != null && (
                <p className="ml-auto font-mono text-xs text-muted-foreground">{improved ? "B better" : a === b ? "same" : "A better"}</p>
              )}
            </div>
            {k === "hit_rate" && (metrics.A?.n_episodes != null || metrics.B?.n_episodes != null) && (
              <div className="mt-2 space-y-0.5 font-mono text-[0.68rem] text-muted-foreground">
                <p>
                  A {cnt(metrics.A, "n_hits")}/{cnt(metrics.A, "n_episodes")} · B {cnt(metrics.B, "n_hits")}/{cnt(metrics.B, "n_episodes")}{" "}
                  {t("backtest.episodes")}
                </p>
                {(metrics.A?.n_forecast_episodes != null || metrics.B?.n_forecast_episodes != null) && (
                  <p>
                    A {cnt(metrics.A, "n_forecast_episodes")} · B {cnt(metrics.B, "n_forecast_episodes")} {t("backtest.forecastEpisodes")}
                  </p>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

const REGION_NAME: Record<string, string> = { delhi_ncr: "Delhi/NCR", punjab_haryana: "Punjab/Haryana" };

function ExploratorySection({ ex }: { ex: ExploratoryRegional }) {
  const { t } = useI18n();
  const regions = Object.keys(ex.alphas?.B ?? ex.alphas?.A ?? {});
  return (
    <section aria-labelledby="expl-title" className="mt-12 rounded-lg border border-dashed border-border p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 id="expl-title" className="text-lg font-semibold">
          {t("backtest.explTitle")}
        </h2>
        <span className="rounded-sm border border-border px-2 py-0.5 font-mono text-[0.7rem] text-muted-foreground">
          {ex.label || t("backtest.explBadge")}
        </span>
      </div>
      <p className="mt-2 max-w-3xl text-sm text-muted-foreground">{t("backtest.explBody")}</p>
      <p className="mt-3 font-mono text-xs text-muted-foreground">
        {regions
          .map((r) => {
            const n = ex.n_stations?.[r];
            return (REGION_NAME[r] ?? r) + (n != null ? " (" + n + " st.)" : "") + ": α_A " + fmtAlpha(ex.alphas.A?.[r]) + " · α_B " + fmtAlpha(ex.alphas.B?.[r]);
          })
          .join("  |  ")}
      </p>
      <MetricTiles metrics={ex.metrics} compact />
      {ex.by_region && (
        <div className="mt-6">
          <h3 className="label-mono">{t("backtest.byRegion")}</h3>
          <div className="mt-1 space-y-4">
            {Object.entries(ex.by_region).map(([r, m]) => (
              <div key={r}>
                <p className="mt-2 text-sm font-medium">{REGION_NAME[r] ?? r}</p>
                <MetricTiles metrics={m} compact />
              </div>
            ))}
          </div>
        </div>
      )}
      {ex.notes?.length > 0 && (
        <div className="mt-6 max-w-4xl space-y-2 text-sm leading-relaxed text-muted-foreground">
          {ex.notes.map((n, i) => (
            <p key={i}>{n}</p>
          ))}
        </div>
      )}
    </section>
  );
}

const fmtAlpha = (v: unknown) => (typeof v === "number" ? (+v.toPrecision(3)).toString() : "-");

/** backtest.json `window` is free-form in CONTRACTS: accept a string or {start,end,...} */
function windowText(w: unknown): string {
  if (!w) return "";
  if (typeof w === "string") return w;
  if (typeof w === "object") {
    const o = w as Record<string, unknown>;
    const day = (v: unknown) => (typeof v === "string" ? v.slice(0, 10) : String(v));
    const start = o.start ?? o.start_utc ?? o.from;
    const end = o.end ?? o.end_utc ?? o.to;
    if (start && end) return `${day(start)} → ${day(end)}`;
    return Object.entries(o)
      .map(([k, v]) =>
        Array.isArray(v) && v.length === 2 ? `${k} ${day(v[0])} → ${day(v[1])}` : typeof v === "string" || typeof v === "number" ? `${k} ${day(v)}` : "",
      )
      .filter(Boolean)
      .join(" · ");
  }
  return "";
}

export function BacktestView() {
  const { t, lang } = useI18n();
  const bt = useBacktest();
  const theme = useThemeName();
  const [view, setView] = useState<"chart" | "table">("chart");
  const c = BACKTEST_COLORS[theme];

  // the replay is published separately from the forecast: keep checking while it's pending
  useEffect(() => {
    if (bt.status !== "missing") return;
    const id = setInterval(() => revalidate(artifactUrl("backtest.json")), 60_000);
    return () => clearInterval(id);
  }, [bt.status]);

  return (
    <div className="mx-auto w-full max-w-6xl px-4 py-8 sm:px-6 lg:py-12">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{t("backtest.title")}</h1>
          <p className="mt-2 text-muted-foreground">{t("backtest.subtitle")}</p>
        </div>
      </header>

      {bt.status === "loading" && <Skeleton className="mt-10 h-64" />}

      {(bt.status === "missing" || bt.status === "error") && (
        <section className="mt-10 rounded-lg border border-dashed border-border p-8">
          <h2 className="text-lg font-semibold">{t("backtest.pending")}</h2>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">{t("backtest.pendingBody")}</p>
        </section>
      )}

      {bt.status === "ready" && (
        <>
          <section aria-labelledby="metrics-title" className="mt-10">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h2 id="metrics-title" className="label-mono">
                {t("backtest.metrics")}
              </h2>
              <span className="font-mono text-[0.7rem] text-muted-foreground">{t("backtest.prereg")}</span>
            </div>
            <MetricTiles metrics={bt.data.metrics} />
            <p className="mt-2 font-mono text-xs text-muted-foreground">
              {windowText(bt.data.window) && <>{windowText(bt.data.window)} · </>}α_A {fmtAlpha(bt.data.calibration?.alpha_A)} · α_B{" "}
              {fmtAlpha(bt.data.calibration?.alpha_B)}
            </p>
            <p className="mt-1 max-w-4xl text-xs leading-relaxed text-muted-foreground">
              {t("backtest.met")}: {bt.data.met_source}
            </p>
          </section>

          <section aria-labelledby="stations-title" className="mt-10">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs" id="stations-title">
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-0.5 w-5" style={{ background: c.obs }} aria-hidden /> {t("backtest.obs")}
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-0 w-5 border-t-[1.5px] border-dashed" style={{ borderColor: c.A }} aria-hidden /> {t("backtest.A")}
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-0.5 w-5" style={{ background: c.B }} aria-hidden /> {t("backtest.B")}
                </span>
              </div>
              <ToggleGroup type="single" size="sm" variant="outline" spacing={0} value={view} onValueChange={(v) => v && setView(v as "chart" | "table")}>
                <ToggleGroupItem value="chart" className="h-7 px-2.5 text-xs">
                  {t("place.viewChart")}
                </ToggleGroupItem>
                <ToggleGroupItem value="table" className="h-7 px-2.5 text-xs">
                  {t("place.viewTable")}
                </ToggleGroupItem>
              </ToggleGroup>
            </div>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              {bt.data.stations.map((st) => (
                <StationChart key={st.id} st={st} view={view} />
              ))}
            </div>
          </section>

          {bt.data.notes && (
            <div className="mt-6 max-w-4xl space-y-2 rounded-md border border-border bg-muted/50 px-4 py-3 text-sm leading-relaxed">
              {(Array.isArray(bt.data.notes) ? bt.data.notes : [bt.data.notes]).map((n, i) => (
                <p key={i}>{n}</p>
              ))}
            </div>
          )}
          {bt.data.exploratory_regional && <ExploratorySection ex={bt.data.exploratory_regional} />}
        </>
      )}

      <div className="mt-12 grid gap-10 md:grid-cols-2">
        <section aria-labelledby="method-title">
          <h2 id="method-title" className="text-lg font-semibold">
            {t("backtest.method")}
          </h2>
          <ol className="mt-3 space-y-2.5 text-sm text-muted-foreground">
            {METHOD[lang].map((m, i) => (
              <li key={i} className="grid grid-cols-[1.25rem_1fr] gap-2">
                <span className="font-mono text-xs leading-5">{i + 1}</span>
                <span>{m}</span>
              </li>
            ))}
          </ol>
        </section>
        <section aria-labelledby="limits-title">
          <h2 id="limits-title" className="text-lg font-semibold">
            {t("backtest.limits")}
          </h2>
          <ul className="mt-3 list-disc space-y-2.5 pl-5 text-sm text-muted-foreground">
            {LIMITS[lang].map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
