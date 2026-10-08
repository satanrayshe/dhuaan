"use client";

import { useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { BACKTEST_COLORS } from "@/lib/colors";
import { useBacktest } from "@/lib/data";
import { useI18n } from "@/lib/i18n";
import { istDate, istDayTime, toMs } from "@/lib/time";
import type { BacktestStation, Lang } from "@/lib/types";
import { useThemeName } from "./bits";

const METRIC_LABELS: Record<string, { label: string; fmt: (v: number) => string; better: "up" | "down" }> = {
  hit_rate: { label: "Hit rate (smoke episodes)", fmt: (v) => `${Math.round(v * 100)}%`, better: "up" },
  false_alarm_ratio: { label: "False-alarm ratio", fmt: (v) => `${Math.round(v * 100)}%`, better: "down" },
  median_lead_h: { label: "Median lead time", fmt: (v) => `${v.toFixed(0)} h`, better: "up" },
  pearson_r: { label: "Pearson r, hourly excess", fmt: (v) => v.toFixed(2), better: "up" },
  r2: { label: "R² after calibration", fmt: (v) => v.toFixed(2), better: "up" },
};

const METHOD: Record<Lang, string[]> = {
  en: [
    "Window 25 Oct to 20 Nov 2025, centred on the 11 Nov 2025 episode. Definitions were fixed before looking at the data.",
    "Observed smoke signal: PM2.5 minus a rolling 7-day 10th-percentile baseline at the same station.",
    "Calibration: least squares PM2.5 excess ≈ α × model smoke, fitted 25 Oct to 5 Nov; scored on 6 to 20 Nov only.",
    "An episode is an excess of at least 60 µg/m³ for 3 or more hours; a hit is a forecast crossing within ±6 h.",
    "A uses VIIRS/MODIS detections only, as official counts do. B adds hourly afternoon geostationary detections. The A-to-B difference is the measured cost of the afternoon gap.",
  ],
  hi: [
    "अवधि 25 अक्टूबर से 20 नवंबर 2025, 11 नवंबर 2025 की घटना पर केंद्रित। परिभाषाएँ डेटा देखने से पहले तय की गईं।",
    "देखा गया धुआँ संकेत: PM2.5 में से उसी स्टेशन की 7-दिन की 10वीं प्रतिशतक आधार रेखा घटाकर।",
    "अंशांकन: 25 अक्टूबर से 5 नवंबर पर न्यूनतम वर्ग; अंक केवल 6 से 20 नवंबर पर।",
    "घटना: कम से कम 3 घंटे तक 60 µg/m³ या अधिक अतिरिक्त; सफलता: ±6 घंटे में पूर्वानुमान का पार होना।",
    "A में केवल VIIRS/MODIS, B में दोपहर बाद के भूस्थिर उपग्रह भी। A और B का अंतर दोपहर बाद की कमी की मापी गई कीमत है।",
  ],
  pa: [
    "ਮਿਆਦ 25 ਅਕਤੂਬਰ ਤੋਂ 20 ਨਵੰਬਰ 2025, 11 ਨਵੰਬਰ 2025 ਦੀ ਘਟਨਾ 'ਤੇ ਕੇਂਦਰਿਤ। ਪਰਿਭਾਸ਼ਾਵਾਂ ਡਾਟਾ ਵੇਖਣ ਤੋਂ ਪਹਿਲਾਂ ਤੈਅ ਕੀਤੀਆਂ।",
    "ਵੇਖਿਆ ਧੂੰਆਂ ਸੰਕੇਤ: PM2.5 ਵਿੱਚੋਂ ਉਸੇ ਸਟੇਸ਼ਨ ਦੀ 7-ਦਿਨ 10ਵੀਂ ਪ੍ਰਤੀਸ਼ਤਕ ਆਧਾਰ ਰੇਖਾ ਘਟਾ ਕੇ।",
    "ਕੈਲੀਬ੍ਰੇਸ਼ਨ: 25 ਅਕਤੂਬਰ ਤੋਂ 5 ਨਵੰਬਰ 'ਤੇ ਘੱਟੋ-ਘੱਟ ਵਰਗ; ਅੰਕ ਸਿਰਫ਼ 6 ਤੋਂ 20 ਨਵੰਬਰ 'ਤੇ।",
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

function StationChart({ st, view }: { st: BacktestStation; view: "chart" | "table" }) {
  const theme = useThemeName();
  const { t, lang } = useI18n();
  const c = BACKTEST_COLORS[theme];
  const config = {
    obs_excess: { label: t("backtest.obs"), color: c.obs },
    pred_A: { label: "A", color: c.A },
    pred_B: { label: "B", color: c.B },
  } satisfies ChartConfig;
  const data = useMemo(() => st.series.map((p) => ({ ...p, ms: toMs(p.t) })), [st]);
  const ticks = useMemo(() => data.filter((_, i) => i % Math.max(1, Math.floor(data.length / 5)) === 0).map((d) => d.ms), [data]);

  return (
    <figure className="min-w-0 rounded-lg border border-border p-4">
      <figcaption className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm font-medium">{st.name}</span>
        <span className="shrink-0 font-mono text-[0.68rem] text-muted-foreground">µg/m³</span>
      </figcaption>
      {view === "chart" ? (
        <ChartContainer config={config} className="mt-2 h-44 w-full">
          <LineChart data={data} margin={{ top: 6, right: 6, bottom: 0, left: 0 }} accessibilityLayer>
            <CartesianGrid vertical={false} stroke="var(--grid-line)" />
            <XAxis
              dataKey="ms"
              type="number"
              domain={["dataMin", "dataMax"]}
              ticks={ticks}
              tickFormatter={(ms: number) => istDate(ms, lang)}
              tickLine={false}
              axisLine={false}
              tick={{ fontSize: 10, fill: "var(--muted-foreground)" }}
            />
            <YAxis tickLine={false} axisLine={false} width={36} tick={{ fontSize: 10, fill: "var(--muted-foreground)" }} />
            <Line dataKey="obs_excess" stroke={c.obs} strokeWidth={2} dot={false} isAnimationActive={false} connectNulls={false} />
            <Line dataKey="pred_A" stroke={c.A} strokeWidth={1.5} dot={false} isAnimationActive={false} strokeDasharray="4 3" />
            <Line dataKey="pred_B" stroke={c.B} strokeWidth={1.5} dot={false} isAnimationActive={false} />
            <ChartTooltip
              cursor={{ stroke: "var(--foreground)", strokeOpacity: 0.25 }}
              content={({ active, payload }) => {
                if (!active || !payload?.length) return null;
                const p = payload[0].payload as (typeof data)[number];
                return (
                  <div className="rounded-md border border-border bg-popover px-2.5 py-2 text-xs shadow-md">
                    <p className="font-medium">{istDayTime(p.ms, lang)} IST</p>
                    {(["obs_excess", "pred_A", "pred_B"] as const).map((k) => (
                      <p key={k} className="mt-0.5 flex items-center gap-1.5 font-mono">
                        <span className="h-0.5 w-3" style={{ background: config[k].color }} aria-hidden />
                        {config[k].label}: {p[k] ?? "n/a"}
                      </p>
                    ))}
                  </div>
                );
              }}
            />
          </LineChart>
        </ChartContainer>
      ) : (
        <ScrollArea className="mt-2 h-44 rounded-md border border-border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>IST</TableHead>
                <TableHead className="text-right">obs</TableHead>
                <TableHead className="text-right">A</TableHead>
                <TableHead className="text-right">B</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody className="font-mono text-xs">
              {data.map((p) => (
                <TableRow key={p.t}>
                  <TableCell className="py-1">{istDayTime(p.ms, lang)}</TableCell>
                  <TableCell className="py-1 text-right">{p.obs_excess ?? "-"}</TableCell>
                  <TableCell className="py-1 text-right">{p.pred_A ?? "-"}</TableCell>
                  <TableCell className="py-1 text-right">{p.pred_B ?? "-"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ScrollArea>
      )}
    </figure>
  );
}

export function BacktestView() {
  const { t, lang } = useI18n();
  const bt = useBacktest();
  const theme = useThemeName();
  const [view, setView] = useState<"chart" | "table">("chart");
  const c = BACKTEST_COLORS[theme];

  const metricKeys = useMemo(() => {
    if (bt.status !== "ready") return [];
    const keys = new Set([...Object.keys(bt.data.metrics.A ?? {}), ...Object.keys(bt.data.metrics.B ?? {})]);
    const numeric = [...keys].filter((k) => typeof (bt.data.metrics.A?.[k] ?? bt.data.metrics.B?.[k]) === "number");
    // known skill metrics first (in a fixed order); raw counts are shown inside the hit-rate tile
    const known = Object.keys(METRIC_LABELS).filter((k) => numeric.includes(k));
    const other = numeric.filter((k) => !(k in METRIC_LABELS) && k !== "episodes" && k !== "hits");
    return [...known, ...other];
  }, [bt]);

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
            <h2 id="metrics-title" className="label-mono">
              {t("backtest.metrics")}
            </h2>
            <div className="mt-3 grid overflow-hidden rounded-lg border border-border sm:grid-cols-2 lg:grid-cols-4 [&>*]:border-border max-sm:[&>*:not(:last-child)]:border-b sm:[&>*]:border-r lg:[&>*:nth-child(4n)]:border-r-0">
              {metricKeys.map((k) => {
                const m = METRIC_LABELS[k] ?? { label: k.replace(/_/g, " "), fmt: (v: number) => String(+v.toFixed(2)), better: "up" as const };
                const a = bt.data.metrics.A?.[k] as number | undefined;
                const b = bt.data.metrics.B?.[k] as number | undefined;
                const improved = a != null && b != null && (m.better === "up" ? b > a : b < a);
                return (
                  <div key={k} className="bg-background p-4">
                    <p className="text-xs text-muted-foreground">{m.label}</p>
                    <div className="mt-2 flex items-baseline gap-4">
                      <div>
                        <p className="font-mono text-[0.68rem] text-muted-foreground">A</p>
                        <p className="text-xl font-semibold tracking-tight">{a != null ? m.fmt(a) : "-"}</p>
                      </div>
                      <div>
                        <p className="font-mono text-[0.68rem] text-muted-foreground">B</p>
                        <p className="text-xl font-semibold tracking-tight">{b != null ? m.fmt(b) : "-"}</p>
                      </div>
                      {a != null && b != null && (
                        <p className="ml-auto font-mono text-xs text-muted-foreground">{improved ? "B better" : a === b ? "same" : "A better"}</p>
                      )}
                    </div>
                    {k === "hit_rate" && bt.data.metrics.A?.episodes != null && (
                      <p className="mt-2 font-mono text-[0.68rem] text-muted-foreground">
                        A {String(bt.data.metrics.A?.hits ?? "-")}/{String(bt.data.metrics.A.episodes)} · B {String(bt.data.metrics.B?.hits ?? "-")}/
                        {String(bt.data.metrics.B?.episodes ?? "-")} episodes
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
            <p className="mt-2 font-mono text-xs text-muted-foreground">
              {t("backtest.met")}: {bt.data.met_source} · α_A {bt.data.calibration.alpha_A} · α_B {bt.data.calibration.alpha_B}
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
            <p className="mt-6 rounded-md border border-border bg-muted/50 px-4 py-3 text-sm">
              {Array.isArray(bt.data.notes) ? bt.data.notes.join(" ") : bt.data.notes}
            </p>
          )}
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
