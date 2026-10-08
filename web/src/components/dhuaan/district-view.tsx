"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";
import { ArrowDownIcon, ArrowUpIcon, DownloadIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useClusters, useFires, useGrid, useMeta, useReceptors } from "@/lib/data";
import { headlineStat, useMediaQuery } from "@/lib/derive";
import { useI18n } from "@/lib/i18n";
import { istDayTime, istTime, toMs } from "@/lib/time";
import type { Cluster } from "@/lib/types";
import { cn } from "@/lib/utils";

const SmokeMap = dynamic(() => import("./smoke-map"), { ssr: false, loading: () => <div className="h-full bg-surface-map" /> });

type SortKey = "rank" | "frp" | "detected";

function csvEscape(v: string | number) {
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

function exportCsv(rows: Cluster[], runId: string) {
  const head = [
    "rank", "cluster_id", "nearest_place", "district", "state", "lat", "lon",
    "first_seen_ist", "last_seen_ist", "n_detections", "frp_sum_mw",
    "exposure_person_hours", "exposure_share_pct", "downwind_places",
  ];
  const ist = (iso: string) => new Date(toMs(iso) + 5.5 * 3600_000).toISOString().slice(0, 16).replace("T", " ");
  const lines = rows.map((c) =>
    [
      c.rank, c.cluster_id, c.nearest_place, c.district, c.state, c.lat, c.lon,
      ist(c.first_seen_utc), ist(c.last_seen_utc), c.n_detections, c.frp_sum_mw.toFixed(1),
      Math.round(c.exposure_person_hours), (c.exposure_share * 100).toFixed(2),
      c.downwind.map((d) => d.name).join("; "),
    ].map(csvEscape).join(","),
  );
  const blob = new Blob([head.join(",") + "\n" + lines.join("\n") + "\n"], { type: "text/csv;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `dhuaan-tonight-${runId}.csv`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

export function DistrictView() {
  const { t, lang } = useI18n();
  const clusters = useClusters();
  const meta = useMeta();
  const fires = useFires();
  const grid = useGrid();
  const idx = useReceptors();
  const isDesktop = useMediaQuery("(min-width: 1024px)", true);
  const [district, setDistrict] = useState<string>("all");
  const [sort, setSort] = useState<{ key: SortKey; dir: 1 | -1 }>({ key: "rank", dir: 1 });
  const [selected, setSelected] = useState<string | null>(null);

  const all = useMemo(() => clusters.data?.clusters ?? [], [clusters.data]);
  const districts = useMemo(() => [...new Set(all.map((c) => c.district))].sort(), [all]);
  const stat = useMemo(() => (all.length ? headlineStat(all) : null), [all]);
  const maxShare = useMemo(() => Math.max(0.0001, ...all.map((c) => c.exposure_share)), [all]);

  const rows = useMemo(() => {
    const r = all.filter((c) => district === "all" || c.district === district);
    const val = (c: Cluster) => (sort.key === "rank" ? c.rank : sort.key === "frp" ? -c.frp_sum_mw : toMs(c.first_seen_utc));
    return [...r].sort((a, b) => (val(a) - val(b)) * sort.dir);
  }, [all, district, sort]);

  const sel = all.find((c) => c.cluster_id === selected) ?? null;
  const placeById = useMemo(() => new Map((idx.data?.places ?? []).map((p) => [p.id, p])), [idx.data]);
  const arcs = useMemo(
    () =>
      sel
        ? sel.downwind
            .map((d) => placeById.get(d.place_id))
            .filter((p): p is NonNullable<typeof p> => !!p)
            .map((p) => ({ id: `${sel.cluster_id}-${p.id}`, from: [sel.lon, sel.lat] as [number, number], to: [p.lon, p.lat] as [number, number], name: p.name }))
        : [],
    [sel, placeById],
  );

  const sortBtn = (key: SortKey, label: string, className?: string) => (
    <TableHead className={className} aria-sort={sort.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        className="inline-flex items-center gap-1 rounded-sm hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        onClick={() => setSort((s) => ({ key, dir: s.key === key ? ((-s.dir) as 1 | -1) : 1 }))}
      >
        {label}
        {sort.key === key && (sort.dir === 1 ? <ArrowUpIcon className="size-3" aria-hidden /> : <ArrowDownIcon className="size-3" aria-hidden />)}
      </button>
    </TableHead>
  );

  return (
    <div className="flex flex-col lg:h-[calc(100dvh-3.5rem)] lg:flex-row lg:overflow-hidden">
      <div className="min-h-0 min-w-0 flex-1 px-4 py-8 sm:px-6 lg:overflow-y-auto lg:py-10">
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{t("district.title")}</h1>
            <p className="mt-2 text-muted-foreground">{t("district.subtitle")}</p>
          </div>
        </header>
        <p className="mt-3 text-xs text-muted-foreground">{t("district.persona")}</p>

        {clusters.status === "loading" && <Skeleton className="mt-8 h-28" />}
        {stat && (
          <section aria-label="Headline" className="mt-8 rounded-lg border border-border p-5">
            <p className="text-2xl leading-snug font-semibold tracking-tight sm:text-3xl">
              {t("district.headline")
                .split(/(\{[knx]\})/)
                .map((part, i) => {
                  const v = part === "{k}" ? stat.k : part === "{n}" ? stat.n : part === "{x}" ? stat.pct : null;
                  return v == null ? <span key={i}>{part}</span> : <span key={i} className="text-smoke">{v}</span>;
                })}
            </p>
            <p className="mt-2 font-mono text-xs text-muted-foreground">
              {t("district.headlineSub", { d: stat.detections.toLocaleString("en-IN") })}
              {meta.data && ` · t0 ${istDayTime(meta.data.t0_utc, lang)} IST`}
            </p>
          </section>
        )}

        <div className="mt-8 flex flex-wrap items-center justify-between gap-3">
          <Select value={district} onValueChange={setDistrict}>
            <SelectTrigger className="w-56" aria-label={t("district.filter")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("district.all")}</SelectItem>
              {districts.map((d) => (
                <SelectItem key={d} value={d}>
                  {d}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex items-center gap-3">
            <p className="hidden text-xs text-muted-foreground md:block">{t("district.hint")}</p>
            <Button variant="outline" size="sm" disabled={!rows.length} onClick={() => exportCsv(rows, meta.data?.run_id ?? "run")}>
              <DownloadIcon aria-hidden /> {t("district.export")}
            </Button>
          </div>
        </div>

        {clusters.status === "ready" && all.length === 0 ? (
          <p className="mt-10 rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground">{t("district.empty")}</p>
        ) : (
          <div className="mt-4 overflow-x-auto rounded-lg border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  {sortBtn("rank", t("district.rank"), "w-14")}
                  <TableHead>{t("district.place")}</TableHead>
                  {sortBtn("detected", t("district.detected"))}
                  {sortBtn("frp", t("district.frp"), "text-right")}
                  <TableHead className="min-w-32">{t("district.exposure")}</TableHead>
                  <TableHead className="min-w-44">{t("district.downwind")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((c) => {
                  const active = c.cluster_id === selected;
                  return (
                    <TableRow
                      key={c.cluster_id}
                      tabIndex={0}
                      aria-selected={active}
                      onClick={() => setSelected(active ? null : c.cluster_id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setSelected(active ? null : c.cluster_id);
                        }
                      }}
                      className={cn("cursor-pointer focus-visible:bg-muted focus-visible:outline-none", active && "bg-smoke-soft hover:bg-smoke-soft")}
                    >
                      <TableCell className="font-mono text-xs">{c.rank}</TableCell>
                      <TableCell>
                        <p className="font-medium">{c.nearest_place}</p>
                        <p className="text-xs text-muted-foreground">
                          {c.district} · <span className="font-mono">{c.lat.toFixed(3)}, {c.lon.toFixed(3)}</span>
                        </p>
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {istDayTime(c.first_seen_utc, lang)}
                        {c.last_seen_utc !== c.first_seen_utc && <span className="text-muted-foreground"> → {istTime(c.last_seen_utc)}</span>}
                        <p className="text-muted-foreground">{c.n_detections}×</p>
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs">{c.frp_sum_mw.toFixed(0)}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span className="relative h-2 flex-1 rounded-[2px] bg-muted" aria-hidden>
                            <span className="absolute inset-y-0 left-0 rounded-[2px] bg-smoke" style={{ width: `${(c.exposure_share / maxShare) * 100}%` }} />
                          </span>
                          <span className="w-12 text-right font-mono text-xs">{(c.exposure_share * 100).toFixed(1)}%</span>
                        </div>
                      </TableCell>
                      <TableCell className="min-w-44 text-xs whitespace-normal">
                        {c.downwind.slice(0, 3).map((d, i) => (
                          <span key={d.place_id}>
                            {i > 0 && ", "}
                            {d.name}
                            {d.arrival_utc && <span className="font-mono text-muted-foreground"> {istTime(d.arrival_utc)}</span>}
                          </span>
                        ))}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </div>

      <div className={cn("relative shrink-0 border-border", isDesktop ? "w-[min(38vw,560px)] border-l" : "h-[60vh] border-t")}>
        {meta.data && (
          <SmokeMap
            className="absolute inset-0"
            ariaLabel={t("map.label")}
            t0={meta.data.t0_utc}
            fires={fires.data}
            grid={grid.data}
            places={idx.data?.places}
            layers={{ fires: true, missed: true, trails: false, field: true, places: true }}
            staticHour={0}
            arcs={arcs}
            highlightCluster={sel ? { lon: sel.lon, lat: sel.lat } : null}
            flyTo={sel ? { lon: sel.lon, lat: sel.lat, zoom: 7.4, key: sel.cluster_id } : null}
            initialZoom={6.4}
          />
        )}
        {sel && (
          <div className="absolute bottom-3 left-3 max-w-[calc(100%-1.5rem)] rounded-md border border-panel-border bg-panel px-3 py-2 text-xs shadow-sm backdrop-blur">
            <p className="font-medium">
              #{sel.rank} · {sel.nearest_place}, {sel.district}
            </p>
            <p className="text-muted-foreground">
              {t("district.downwind")}: {sel.downwind.map((d) => d.name).join(", ")}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
