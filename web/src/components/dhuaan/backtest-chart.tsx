"use client";

import { useMemo } from "react";
import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts";
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { BACKTEST_COLORS } from "@/lib/colors";
import { useI18n } from "@/lib/i18n";
import { istDate, istDayTime, toMs } from "@/lib/time";
import type { BacktestStation } from "@/lib/types";
import { useThemeName } from "./bits";

export function StationChart({ st, view }: { st: BacktestStation; view: "chart" | "table" }) {
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
