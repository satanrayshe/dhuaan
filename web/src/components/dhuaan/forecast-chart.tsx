"use client";

import { useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { naqiFromPm25 } from "@/lib/colors";
import { useI18n } from "@/lib/i18n";
import { playback } from "@/lib/playback";
import { H_MIN, HOUR_MS, istDayTime, istHourOf, isNightIst, toMs } from "@/lib/time";
import { alphaFor } from "@/lib/regions";
import type { Meta, PlaceDetail } from "@/lib/types";
import { NaqiChip, SectionLabel } from "./bits";

interface Row {
  h: number;
  ms: number;
  median: number;
  band: [number, number];
}

const config = {
  median: { label: "Median", color: "var(--smoke)" },
  band: { label: "p10-p90", color: "var(--smoke)" },
} satisfies ChartConfig;

export function ForecastChart({
  place,
  meta,
  cursorHour,
  height = 200,
}: {
  place: PlaceDetail;
  meta?: Meta;
  cursorHour?: number | null;
  height?: number;
}) {
  const { t, lang } = useI18n();
  const [view, setView] = useState<"chart" | "table">("chart");
  const calibrated = !!meta?.calibrated;
  const k = calibrated ? alphaFor(meta, place.district, place.state) : 1;
  const unit = calibrated ? "µg/m³" : "";
  const t0ms = toMs(place.t0_utc);

  const rows = useMemo<Row[]>(
    () =>
      place.series.map((v, i) => ({
        h: i + H_MIN,
        ms: t0ms + (i + H_MIN) * HOUR_MS,
        median: +(v * k).toFixed(calibrated ? 0 : 2),
        band: [+(place.p10[i] * k).toFixed(calibrated ? 0 : 2), +(place.p90[i] * k).toFixed(calibrated ? 0 : 2)],
      })),
    [place, k, t0ms, calibrated],
  );

  const nights = useMemo(() => {
    const out: [number, number][] = [];
    let start: number | null = null;
    for (const r of rows) {
      const n = isNightIst(r.ms);
      if (n && start === null) start = r.h;
      if (!n && start !== null) {
        out.push([start, r.h]);
        start = null;
      }
    }
    if (start !== null) out.push([start, rows[rows.length - 1].h]);
    return out;
  }, [rows]);

  // ticks at IST midnights
  const ticks = useMemo(() => rows.filter((r) => Math.abs(istHourOf(r.ms)) < 0.5).map((r) => r.h), [rows]);
  const yMax = Math.max(1, ...rows.map((r) => r.band[1]));
  const naqiLines = calibrated ? [60, 90, 120, 250].filter((v) => v < yMax * 1.05) : [];

  return (
    <section aria-labelledby={`fc-${place.id}`}>
      <div className="mb-2 flex items-center justify-between gap-2">
        <SectionLabel id={`fc-${place.id}`}>
          {t("place.forecast")} · {calibrated ? t("place.estPm") : `${t("place.smokeIndex")} (${t("place.uncalibrated")})`}
          {calibrated && <span className="normal-case"> µg/m³</span>}
        </SectionLabel>
        <ToggleGroup
          type="single"
          size="sm"
          variant="outline"
          spacing={0}
          value={view}
          onValueChange={(v) => v && setView(v as "chart" | "table")}
          aria-label={`${t("place.viewChart")} / ${t("place.viewTable")}`}
        >
          <ToggleGroupItem value="chart" className="h-6 px-2 text-[0.7rem]">
            {t("place.viewChart")}
          </ToggleGroupItem>
          <ToggleGroupItem value="table" className="h-6 px-2 text-[0.7rem]">
            {t("place.viewTable")}
          </ToggleGroupItem>
        </ToggleGroup>
      </div>

      {view === "chart" ? (
        <>
          <ChartContainer config={config} className="w-full" style={{ height }}>
            <ComposedChart
              data={rows}
              margin={{ top: 8, right: 8, bottom: 0, left: -12 }}
              onClick={(e) => {
                const h = Number((e as { activeLabel?: number | string } | null)?.activeLabel);
                if (Number.isFinite(h)) playback.setHour(h);
              }}
              accessibilityLayer
            >
              <CartesianGrid vertical={false} stroke="var(--grid-line)" />
              {nights.map(([a, b]) => (
                <ReferenceArea key={a} x1={a} x2={b} fill="var(--night)" fillOpacity={1} stroke="none" ifOverflow="hidden" />
              ))}
              <XAxis
                dataKey="h"
                type="number"
                domain={[H_MIN, 72]}
                ticks={ticks}
                tickFormatter={(h: number) => istDayTime(t0ms + h * HOUR_MS, lang).split(" ")[0]}
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
              />
              <YAxis
                width={44}
                tickLine={false}
                axisLine={false}
                tick={{ fontSize: 11, fill: "var(--muted-foreground)" }}
                domain={[0, "auto"]}
                allowDecimals={!calibrated}
              />
              {naqiLines.map((v) => (
                <ReferenceLine
                  key={v}
                  y={v}
                  stroke="var(--muted-foreground)"
                  strokeOpacity={0.35}
                  strokeDasharray="2 3"
                  label={{
                    value: String(v),
                    position: "insideTopRight",
                    fontSize: 10,
                    fill: "var(--muted-foreground)",
                  }}
                />
              ))}
              <Area dataKey="band" type="monotone" stroke="none" fill="var(--smoke)" fillOpacity={0.2} isAnimationActive={false} />
              <Line dataKey="median" type="monotone" stroke="var(--smoke)" strokeWidth={2} dot={false} isAnimationActive={false} />
              <ReferenceLine
                x={0}
                stroke="var(--foreground)"
                strokeWidth={1}
                label={{ value: t("place.now"), position: "insideTopLeft", fontSize: 10, fill: "var(--foreground)" }}
              />
              {cursorHour != null && cursorHour !== 0 && (
                <ReferenceLine x={cursorHour} stroke="var(--foreground)" strokeOpacity={0.5} strokeDasharray="3 3" />
              )}
              <ChartTooltip
                cursor={{ stroke: "var(--foreground)", strokeOpacity: 0.25 }}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null;
                  const r = payload[0].payload as Row;
                  return (
                    <div className="rounded-md border border-border bg-popover px-2.5 py-2 text-xs shadow-md">
                      <p className="font-medium">
                        {istDayTime(r.ms, lang)} IST
                        <span className="ml-1.5 font-mono font-normal text-muted-foreground">
                          {r.h >= 0 ? "+" : ""}
                          {r.h} h
                        </span>
                      </p>
                      <p className="mt-1 font-mono">
                        {t("place.median")} {r.median} {unit}
                      </p>
                      <p className="font-mono text-muted-foreground">
                        {t("place.band")} {r.band[0]} to {r.band[1]}
                      </p>
                      {calibrated && <NaqiChip category={naqiFromPm25(r.median)} size="sm" className="mt-1.5" />}
                    </div>
                  );
                }}
              />
            </ComposedChart>
          </ChartContainer>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-[0.7rem] text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-4 rounded-full bg-smoke" aria-hidden /> {t("place.median")}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-4 rounded-[2px] bg-smoke/25" aria-hidden /> {t("place.band")} ({t("place.members", { n: meta?.members ?? 5 })})
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-4 rounded-[2px] bg-[var(--night)] ring-1 ring-border" aria-hidden /> {t("place.night")}
            </span>
          </div>
        </>
      ) : (
        <ScrollArea className="rounded-md border border-border" style={{ height: height + 24 }}>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("place.hour")}</TableHead>
                <TableHead className="text-right">{t("place.median")}</TableHead>
                <TableHead className="text-right">p10</TableHead>
                <TableHead className="text-right">p90</TableHead>
                {calibrated && <TableHead>NAQI</TableHead>}
              </TableRow>
            </TableHeader>
            <TableBody className="font-mono text-xs">
              {rows
                .filter((r) => r.h >= 0)
                .map((r) => (
                  <TableRow key={r.h}>
                    <TableCell className="py-1">{istDayTime(r.ms, lang)}</TableCell>
                    <TableCell className="py-1 text-right">{r.median}</TableCell>
                    <TableCell className="py-1 text-right text-muted-foreground">{r.band[0]}</TableCell>
                    <TableCell className="py-1 text-right text-muted-foreground">{r.band[1]}</TableCell>
                    {calibrated && (
                      <TableCell className="py-1">
                        <NaqiChip category={naqiFromPm25(r.median)} size="sm" />
                      </TableCell>
                    )}
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </ScrollArea>
      )}
    </section>
  );
}

// kept for existing imports; lives in its own module so it does not pull in Recharts
export { AttributionBars } from "./attribution-bars";
