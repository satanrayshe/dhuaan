"use client";

import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { AlertTriangleIcon, FlameIcon, RotateCwIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Drawer, DrawerContent, DrawerTitle } from "@/components/ui/drawer";
import { Skeleton } from "@/components/ui/skeleton";
import { artifactUrl, isStale, reload, useClusters, useFires, useGrid, useMeta, useReceptors, useTrips } from "@/lib/data";
import { abroadCentroid, hasEveningLayer, missedByMidday, useMediaQuery } from "@/lib/derive";
import { useI18n } from "@/lib/i18n";
import { playback, useReducedMotionFlag } from "@/lib/playback";
import { ageLabel, H_MAX, H_MIN, istDayTime, istTime, toMs } from "@/lib/time";
import { CoachMarks } from "./coach-marks";
import { LayerPanel } from "./layer-panel";
import { setSearchOpen } from "./place-search";
import type { FlyTarget, MapLayersState } from "./smoke-map";
import { TimeScrubber } from "./time-scrubber";

// the place card pulls in Recharts; load it only when a place is opened
const PlaceCard = dynamic(() => import("./place-card").then((m) => m.PlaceCard), {
  ssr: false,
  loading: () => <div className="h-96 animate-pulse bg-muted/40" />,
});

const SmokeMap = dynamic(() => import("./smoke-map"), {
  ssr: false,
  loading: () => <div className="absolute inset-0 bg-surface-map" />,
});

function SplitHandle({ value, onChange }: { value: number; onChange: (v: number) => void }) {
  const { t } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const drag = (e: React.PointerEvent) => {
    const parent = ref.current?.parentElement;
    if (!parent) return;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    const move = (ev: PointerEvent) => {
      const r = parent.getBoundingClientRect();
      onChange(Math.max(0.05, Math.min(0.95, (ev.clientX - r.left) / r.width)));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
  };
  return (
    <div ref={ref} className="pointer-events-none absolute inset-y-0 z-10" style={{ left: `${value * 100}%` }}>
      <div className="absolute inset-y-0 -left-px w-0.5 bg-foreground/80" />
      <div className="absolute top-16 right-3 rounded-sm bg-panel px-2 py-1 font-mono text-[0.68rem] whitespace-nowrap shadow-sm">{t("compare.left")}</div>
      <div className="absolute top-16 left-3 rounded-sm bg-panel px-2 py-1 font-mono text-[0.68rem] whitespace-nowrap shadow-sm">{t("compare.right")}</div>
      <div
        role="slider"
        tabIndex={0}
        aria-label={t("compare.handle")}
        aria-valuemin={5}
        aria-valuemax={95}
        aria-valuenow={Math.round(value * 100)}
        onPointerDown={drag}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft") onChange(Math.max(0.05, value - 0.03));
          if (e.key === "ArrowRight") onChange(Math.min(0.95, value + 0.03));
        }}
        className="pointer-events-auto absolute top-1/2 -left-4 flex h-12 w-8 -translate-y-1/2 cursor-ew-resize items-center justify-center rounded-md border border-border bg-background shadow-md focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
      >
        <span className="flex gap-0.5" aria-hidden>
          <span className="h-5 w-px bg-foreground/60" />
          <span className="h-5 w-px bg-foreground/60" />
        </span>
      </div>
    </div>
  );
}

const noop = () => () => {};

// desktop is landscape: Lahore's fires to Delhi. Phones are portrait and width-bound, so take
// in the western fires (and the "across the border" note) and let the height run long.
const HOME_BOUNDS: [[number, number], [number, number]] = [
  [73.55, 28.3],
  [77.55, 32.1],
];
const HOME_BOUNDS_PHONE: [[number, number], [number, number]] = [
  [72.6, 28.4],
  [77.45, 32.2],
];

export const DEMO_IDS = { school: "osm-w1090680897", ward: "dlw-21", town: "gn-1260107" } as const;

export function MapApp() {
  const { t, lang } = useI18n();
  const router = useRouter();
  const params = useSearchParams();
  const placeId = params.get("place");
  const isDesktop = useMediaQuery("(min-width: 1024px)", true);
  const reducedMotion = useReducedMotionFlag();

  const meta = useMeta();
  const fires = useFires();
  const grid = useGrid();
  // after hydration only: the server snapshot can't know the reduced-motion preference
  const hydrated = useSyncExternalStore(noop, () => true, () => false);
  const trips = useTrips(hydrated && !reducedMotion);
  const idx = useReceptors();
  const clusters = useClusters();

  const [layers, setLayers] = useState<MapLayersState>({ fires: true, missed: true, trails: true, field: true, places: true });
  // ?split=1 opens the midday-vs-evening comparison, ?autoplay=1 starts playback (demo recording links)
  const [compare, setCompare] = useState(() => params.get("split") === "1");
  const [split, setSplit] = useState(0.5);

  const t0 = meta.data?.t0_utc ?? grid.data?.t0_utc;
  const evening = hasEveningLayer(fires.data);
  const missed = useMemo(() => missedByMidday(fires.data), [fires.data]);
  // an empty geostationary layer is a real state (no evening fires yet), not a broken layer
  const eveningNote = useMemo(() => {
    if (evening) return undefined;
    const geo = meta.data?.sources.find((s) => /LSA SAF|MSG|IODC/i.test(s.name));
    const last = geo?.latest_obs_utc ? t("layers.missedLast", { t: istTime(geo.latest_obs_utc) }) : "";
    return t("layers.missedNone", { last });
  }, [evening, meta.data, t]);
  const borderLabel = useMemo(() => {
    const c = abroadCentroid(clusters.data?.clusters);
    return c ? { lon: c.lon, lat: c.lat, text: `${t("map.border")}
${t("map.borderSub")}` } : null;
  }, [clusters.data, t]);

  // start the clock at "now" relative to the run, once
  const started = useRef(false);
  useEffect(() => {
    if (!t0 || started.current) return;
    started.current = true;
    const from = Number(params.get("from"));
    const h = Number.isFinite(from) && params.has("from") ? from : Math.round((Date.now() - toMs(t0)) / 3600_000);
    playback.setHour(Math.max(H_MIN, Math.min(H_MAX, h)));
    if (params.get("autoplay") === "1") playback.play();
  }, [t0, params]);

  const selected = useMemo(() => idx.data?.places.find((p) => p.id === placeId) ?? null, [idx.data, placeId]);
  const [fly, setFly] = useState<FlyTarget | null>(null);
  const lastFlown = useRef<string | null>(null);
  useEffect(() => {
    if (selected && lastFlown.current !== selected.id) {
      lastFlown.current = selected.id;
      setFly({ lon: selected.lon, lat: selected.lat, zoom: 8.25, key: selected.id });
    }
  }, [selected]);

  const select = (id: string | null) => {
    router.replace(id ? `/?place=${encodeURIComponent(id)}` : "/", { scroll: false });
  };

  const coreError = [meta, fires, grid].find((r) => r.status === "error" || r.status === "missing");
  const loading = !t0 && !coreError;
  const stale = isStale(meta.data);
  const noFires = fires.status === "ready" && fires.data.features.length === 0;
  const panelOpen = isDesktop;

  const quickPicks = useMemo(() => {
    const ps = idx.data?.places ?? [];
    const byId = (id: string) => ps.find((p) => p.id === id);
    const find = (re: RegExp, kind?: string) => ps.find((p) => re.test(p.name) && (!kind || p.kind === kind));
    // the demo places (backend/data/demo_places.json), by id first, by name as a fallback
    const picks = [
      byId(DEMO_IDS.school) ?? find(/bhawanigarh/i, "school"),
      byId(DEMO_IDS.ward) ?? find(/rohini/i, "ward"),
      byId(DEMO_IDS.town) ?? find(/^patiala$/i, "city"),
    ].filter(Boolean);
    const top = [...ps].filter((p) => !picks.includes(p)).sort((a, b) => b.peak_smoke - a.peak_smoke).slice(0, 4);
    return { picks: picks as typeof ps, top };
  }, [idx.data]);

  return (
    <div className="relative flex h-[calc(100dvh-3.5rem)] min-h-[520px] overflow-hidden">
      <div className="map-home relative min-w-0 flex-1">
        {t0 && (
          <SmokeMap
            className="absolute inset-0"
            ariaLabel={t("map.label")}
            t0={t0}
            fires={fires.data}
            trips={trips.data}
            grid={grid.data}
            places={idx.data?.places}
            layers={{ ...layers, missed: layers.missed && evening }}
            borderLabel={borderLabel}
            selectedPlaceId={placeId}
            onPickPlace={(id) => select(id)}
            splitAt={compare && evening ? split : null}
            flyTo={fly}
            reducedMotion={reducedMotion}
            initialZoom={isDesktop ? 6.7 : 5.7}
            // the story on load: fires in both Punjabs (west) to Delhi (south-east), clear of the scrubber
            initialBounds={isDesktop ? HOME_BOUNDS : HOME_BOUNDS_PHONE}
            initialPadding={isDesktop ? { top: 28, bottom: 170, left: 28, right: 72 } : { top: 64, bottom: 190, left: 8, right: 8 }}
          />
        )}

        {loading && (
          <div className="absolute inset-0 grid place-items-center bg-surface-map">
            <div className="flex flex-col items-center gap-3" aria-busy="true">
              <Skeleton className="h-2 w-40" />
              <p className="text-sm text-muted-foreground">{t("map.loading")}…</p>
            </div>
          </div>
        )}
        {coreError && (
          <div className="absolute inset-0 grid place-items-center bg-surface-map p-6">
            <div className="max-w-sm rounded-lg border border-border bg-background p-5 text-center">
              <AlertTriangleIcon className="mx-auto size-5 text-destructive" aria-hidden />
              <p className="mt-2 text-sm">{t("map.error")}</p>
              <Button
                className="mt-3"
                variant="outline"
                size="sm"
                onClick={() => ["meta.json", "fires.geojson", "grid.json"].forEach((n) => reload(artifactUrl(n)))}
              >
                <RotateCwIcon aria-hidden /> {t("map.retry")}
              </Button>
            </div>
          </div>
        )}

        {t0 && (
          <>
            {/* desktop: chrome sits over the quiet eastern hills; the burning is in the west */}
            <div className="absolute top-3 left-3 z-10 flex max-w-[calc(100%-4.5rem)] flex-col items-start gap-2 lg:right-16 lg:left-auto lg:items-end">
              <LayerPanel
                key={isDesktop ? "desktop" : "mobile"}
                defaultOpen={isDesktop}
                layers={layers}
                setLayers={setLayers}
                hasEvening={evening}
                eveningNote={eveningNote}
                compare={compare}
                setCompare={setCompare}
                reducedMotion={reducedMotion}
              />
            </div>

            {(stale || (evening && layers.missed && missed > 0) || noFires) && (
              <div className="pointer-events-none absolute top-3 left-1/2 z-10 flex w-[min(30rem,calc(100%-2rem))] -translate-x-1/2 flex-col items-center gap-2 max-lg:top-14">
                {stale && meta.data && (
                  <p className="pointer-events-auto flex items-center gap-2 rounded-md border border-destructive/40 bg-background px-3 py-1.5 text-xs text-destructive shadow-sm">
                    <AlertTriangleIcon className="size-3.5" aria-hidden />
                    {t("stale.banner", { age: ageLabel(meta.data.generated_utc) })}
                  </p>
                )}
                {noFires && (
                  <p className="pointer-events-auto rounded-md border border-border bg-background px-3 py-1.5 text-sm shadow-sm">{t("map.noFires")}</p>
                )}
                {evening && layers.missed && missed > 0 && (
                  <p className="pointer-events-auto hidden items-center gap-2 rounded-md border border-panel-border bg-panel px-3 py-1.5 text-sm shadow-sm backdrop-blur md:flex">
                    <span className="size-3 shrink-0 rounded-full border-[1.5px] border-fire" aria-hidden />
                    <span>
                      {t("map.missedTile")
                        .split("{n}")
                        .map((part, i) => (
                          <span key={i}>
                            {i > 0 && <span className="font-semibold">{missed}</span>}
                            {part}
                          </span>
                        ))}
                    </span>
                  </p>
                )}
              </div>
            )}

            {compare && evening && <SplitHandle value={split} onChange={setSplit} />}

            {/* desktop: left-aligned so the basemap attribution (bottom-right) stays readable */}
            <div className="absolute inset-x-2 bottom-2 z-10 sm:inset-x-3 sm:bottom-3 lg:right-auto lg:w-[min(46rem,calc(100%-19rem))]">
              <TimeScrubber t0={t0} blh={grid.data?.blh_m} />
            </div>
          </>
        )}
      </div>

      {panelOpen && (
        <aside className="w-[408px] shrink-0 overflow-y-auto border-l border-border bg-background" aria-label={selected?.name ?? t("place.pick")}>
          {placeId ? (
            <PlaceCard placeId={placeId} onClose={() => select(null)} />
          ) : (
            <div className="space-y-6 p-5">
              <div>
                <h1 className="text-2xl leading-tight font-semibold tracking-tight">{t("brand.tagline")}</h1>
                <p className="mt-2 text-sm text-muted-foreground">{t("place.pick")}</p>
              </div>
              <Button variant="outline" className="w-full justify-start" onClick={() => setSearchOpen(true)}>
                {t("search.placeholder")}
              </Button>
              {quickPicks.picks.length > 0 && (
                <PickList title={t("place.try")} items={quickPicks.picks} onPick={select} lang={lang} />
              )}
              {quickPicks.top.length > 0 && (
                <PickList title={t("place.topPeaks")} items={quickPicks.top} onPick={select} lang={lang} showPeak />
              )}
              {fires.data && (
                <p className="flex items-center gap-2 text-xs text-muted-foreground">
                  <FlameIcon className="size-3.5 text-fire" aria-hidden />
                  {fires.data.features.length.toLocaleString("en-IN")} detections · t0 {t0 ? istDayTime(t0, lang) : ""} IST
                </p>
              )}
            </div>
          )}
        </aside>
      )}

      {!isDesktop && (
        <Drawer open={!!placeId} onOpenChange={(o) => !o && select(null)}>
          <DrawerContent className="max-h-[88dvh]">
            <DrawerTitle className="sr-only">{selected?.name ?? "Place"}</DrawerTitle>
            <div className="overflow-y-auto">{placeId && <PlaceCard placeId={placeId} onClose={() => select(null)} />}</div>
          </DrawerContent>
        </Drawer>
      )}

      <CoachMarks ready={!!t0 && (isDesktop || !placeId)} />
    </div>
  );
}

function PickList({
  title,
  items,
  onPick,
  lang,
  showPeak,
}: {
  title: string;
  items: { id: string; name: string; district: string; kind: string; peak_utc: string; arrival_utc: string | null }[];
  onPick: (id: string) => void;
  lang: "en" | "hi" | "pa";
  showPeak?: boolean;
}) {
  const { t } = useI18n();
  return (
    <div>
      <h2 className="label-mono">{title}</h2>
      <ul className="mt-2 divide-y divide-border rounded-md border border-border">
        {items.map((p) => (
          <li key={p.id}>
            <button
              type="button"
              onClick={() => onPick(p.id)}
              className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left transition-colors hover:bg-muted focus-visible:bg-muted focus-visible:outline-none"
            >
              <span className="min-w-0">
                <span className="block truncate text-sm">{p.name}</span>
                <span className="block truncate text-xs text-muted-foreground">{p.district}</span>
              </span>
              <span className="shrink-0 text-right font-mono text-xs text-muted-foreground">
                {showPeak
                  ? `${t("place.peak")} ${istDayTime(p.peak_utc, lang)}`
                  : p.arrival_utc
                    ? istDayTime(p.arrival_utc, lang)
                    : t("search.noSmoke")}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
