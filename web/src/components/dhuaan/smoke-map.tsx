"use client";

import { MapboxOverlay } from "@deck.gl/mapbox";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { TripsLayer } from "@deck.gl/geo-layers";
import { useTheme } from "next-themes";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Map as MapView, MapArc, MapControls, useMap, type MapArcDatum } from "@/components/ui/map";
import { FIRE_COLOR, SMOKE_RAMP, TRAIL_COLOR, hexToRgb, smokeLut, type ThemeName } from "@/lib/colors";
import { playback } from "@/lib/playback";
import { H_MIN, istTime, toMs } from "@/lib/time";
import type { FiresGeoJSON, GridFile, PlaceIndexEntry, TripsFile } from "@/lib/types";

export interface MapLayersState {
  fires: boolean;
  missed: boolean;
  trails: boolean;
  field: boolean;
  places: boolean;
}

export interface FlyTarget {
  lon: number;
  lat: number;
  zoom?: number;
  /** changes to re-trigger the same target */
  key: string | number;
}

export interface SmokeMapProps {
  t0: string;
  fires?: FiresGeoJSON;
  trips?: TripsFile;
  grid?: GridFile;
  places?: PlaceIndexEntry[];
  layers: MapLayersState;
  selectedPlaceId?: string | null;
  onPickPlace?: (id: string) => void;
  /** fraction 0..1 of map width; when set, evening detections only render right of it */
  splitAt?: number | null;
  flyTo?: FlyTarget | null;
  arcs?: (MapArcDatum & { name: string })[];
  highlightCluster?: { lon: number; lat: number } | null;
  reducedMotion?: boolean;
  initialZoom?: number;
  initialCenter?: [number, number];
  className?: string;
  /** geo-anchored note over fires outside India ("Across the border / Pakistani Punjab") */
  borderLabel?: { lon: number; lat: number; text: string } | null;
  /** draw smoke and pins beneath the basemap's place labels (default true) */
  labelsOnTop?: boolean;
  /** show smoke at a fixed hour instead of following playback (district view) */
  staticHour?: number | null;
  ariaLabel: string;
}

// west of centre: most of this season's burning sits in the two Punjabs
const INITIAL_CENTER: [number, number] = [75.55, 30.1];

function decodeFrames(grid: GridFile): Uint8Array[] {
  return grid.frames.map((b64) => {
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  });
}

/** LRU of rendered smoke canvases keyed by theme + quantised minute */
class FrameCache {
  private map = new globalThis.Map<string, HTMLCanvasElement>();
  constructor(private max = 48) {}
  get(key: string, make: () => HTMLCanvasElement) {
    let c = this.map.get(key);
    if (c) {
      this.map.delete(key);
      this.map.set(key, c);
      return c;
    }
    c = make();
    this.map.set(key, c);
    if (this.map.size > this.max) this.map.delete(this.map.keys().next().value!);
    return c;
  }
  clear() {
    this.map.clear();
  }
}

type TripRow = TripsFile["trips"][number];

/**
 * trips.json is sampled hourly (small on the wire). Re-densify each path with a uniform
 * Catmull-Rom spline (`k` sub-steps per hour) so trails curve instead of zig-zagging when
 * zoomed in. Timestamps are interpolated linearly; done once per file.
 */
function smoothTrips(trips: TripRow[], k = 3): TripRow[] {
  return trips.map((tr) => {
    const P = tr.path, T = tr.ts, n = P.length;
    if (n < 3) return tr;
    const path: [number, number][] = [];
    const ts: number[] = [];
    for (let i = 0; i < n - 1; i++) {
      const p0 = P[Math.max(0, i - 1)], p1 = P[i], p2 = P[i + 1], p3 = P[Math.min(n - 1, i + 2)];
      for (let s = 0; s < k; s++) {
        const u = s / k, u2 = u * u, u3 = u2 * u;
        const c = (a: number, b: number, cc: number, d: number) =>
          0.5 * (2 * b + (-a + cc) * u + (2 * a - 5 * b + 4 * cc - d) * u2 + (-a + 3 * b - 3 * cc + d) * u3);
        path.push([c(p0[0], p1[0], p2[0], p3[0]), c(p0[1], p1[1], p2[1], p3[1])]);
        ts.push(T[i] + (T[i + 1] - T[i]) * u);
      }
    }
    path.push(P[n - 1]);
    ts.push(T[n - 1]);
    return { cluster_id: tr.cluster_id, path, ts };
  });
}

/** alpha falloff over the outer cells, so the model domain edge doesn't read as a hard wall of smoke */
function edgeFade(i: number, j: number, nx: number, ny: number, cells = 4) {
  const d = Math.min(i + 0.5, nx - i - 0.5, j + 0.5, ny - j - 0.5);
  return d >= cells ? 1 : (d / cells) ** 1.5;
}

type MlMap = NonNullable<ReturnType<typeof useMap>["map"]>;
const FIELD_SRC = "dhuaan-smoke-field";

/**
 * The smoke field as a maplibre canvas source + raster layer inserted beneath the first
 * symbol layer, so basemap place names stay legible on top of dense smoke. The deck.gl
 * overlay (trails, fires, pins) still draws above. Repaints only when the frame changes.
 */
function useFieldSource(map: MlMap | null, grid: GridFile | undefined, belowLabels: boolean) {
  const st = useRef<{ canvas: HTMLCanvasElement | null; key: string | null; visible: boolean }>({ canvas: null, key: null, visible: true });
  useEffect(() => {
    if (!map || !grid) return;
    const state = st.current;
    if (process.env.NODE_ENV !== "production") (window as unknown as { __dhuaanMap: unknown }).__dhuaanMap = map;
    const c = document.createElement("canvas");
    c.width = grid.nx;
    c.height = grid.ny;
    state.canvas = c;
    state.key = null;
    const coords: [[number, number], [number, number], [number, number], [number, number]] = [
      [grid.lon0, grid.lat0 + grid.ny * grid.dlat],
      [grid.lon0 + grid.nx * grid.dlon, grid.lat0 + grid.ny * grid.dlat],
      [grid.lon0 + grid.nx * grid.dlon, grid.lat0],
      [grid.lon0, grid.lat0],
    ];
    const ensure = () => {
      // isStyleLoaded() also waits for every tile; addSource only needs the style JSON
      if (!map.style || map.getSource(FIELD_SRC)) return;
      try {
        map.addSource(FIELD_SRC, { type: "canvas", canvas: c, coordinates: coords, animate: false });
      } catch {
        return; // style JSON still loading; the next styledata/idle event retries
      }
      const before = belowLabels ? map.getStyle().layers?.find((l) => l.type === "symbol")?.id : undefined;
      map.addLayer(
        {
          id: FIELD_SRC,
          type: "raster",
          source: FIELD_SRC,
          layout: { visibility: state.visible ? "visible" : "none" },
          paint: { "raster-resampling": "linear", "raster-fade-duration": 0, "raster-opacity": 1 },
        },
        before,
      );
    };
    ensure();
    // theme switches reload the basemap style and drop custom layers: put it back
    map.on("styledata", ensure);
    map.on("idle", ensure);
    return () => {
      map.off("styledata", ensure);
      map.off("idle", ensure);
      try {
        if (map.getLayer(FIELD_SRC)) map.removeLayer(FIELD_SRC);
        if (map.getSource(FIELD_SRC)) map.removeSource(FIELD_SRC);
      } catch {}
      state.canvas = null;
    };
  }, [map, grid, belowLabels]);

  return useMemo(
    () => ({
      paint(key: string, frame: HTMLCanvasElement) {
        const c = st.current.canvas;
        if (!c || !map || st.current.key === key) return;
        st.current.key = key;
        const ctx = c.getContext("2d")!;
        ctx.clearRect(0, 0, c.width, c.height);
        ctx.drawImage(frame, 0, 0);
        const src = map.getSource(FIELD_SRC) as { play?: () => void; pause?: () => void } | undefined;
        // play() marks the texture dirty and repaints; pause() uploads it once and stops
        src?.play?.();
        src?.pause?.();
      },
      setVisible(v: boolean) {
        if (st.current.visible === v || !map) return;
        st.current.visible = v;
        if (map.getLayer(FIELD_SRC)) map.setLayoutProperty(FIELD_SRC, "visibility", v ? "visible" : "none");
      },
    }),
    [map],
  );
}

function Overlay(props: SmokeMapProps & { theme: ThemeName }) {
  const { map, isLoaded } = useMap();
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const propsRef = useRef(props);
  const [zoom, setZoom] = useState(6.5);
  const [splitLon, setSplitLon] = useState<number | null>(null);

  const { fires, grid, trips, places, theme, splitAt } = props;
  const field = useFieldSource(map, grid, props.labelsOnTop !== false);

  // derived, memoised data
  const fireRows = useMemo(
    () =>
      (fires?.features ?? []).map((f) => ({
        lon: f.geometry.coordinates[0],
        lat: f.geometry.coordinates[1],
        ms: toMs(f.properties.acq_utc),
        p: f.properties,
      })),
    [fires],
  );
  const frames = useMemo(() => (grid ? decodeFrames(grid) : null), [grid]);
  const tripRows = useMemo(() => (trips ? smoothTrips(trips.trips) : null), [trips]);
  const cache = useMemo(() => new FrameCache(), []);
  useEffect(() => () => cache.clear(), [cache, frames, theme]);
  const lut = useMemo(() => smokeLut(theme), [theme]);

  // keep zoom + split longitude in React state (coarse)
  useEffect(() => {
    if (!map) return;
    const onZoom = () => setZoom(Math.round(map.getZoom() * 4) / 4);
    const onMove = () => {
      if (splitAt == null) return setSplitLon(null);
      const c = map.getCanvas();
      const x = (c.clientWidth || c.width) * splitAt;
      setSplitLon(map.unproject([x, (c.clientHeight || c.height) / 2]).lng);
    };
    onZoom();
    onMove();
    map.on("zoomend", onZoom);
    map.on("move", onMove);
    return () => {
      map.off("zoomend", onZoom);
      map.off("move", onMove);
    };
  }, [map, splitAt]);

  // last result per key: stable array identities across animation frames
  const memo = useRef(new globalThis.Map<string, { key: string; value: unknown }>());
  const keep = <T,>(key: string, make: () => T): T => {
    const slot = key.slice(0, key.indexOf(":"));
    const hit = memo.current.get(slot);
    if (hit && hit.key === key) return hit.value as T;
    const value = make();
    memo.current.set(slot, { key, value });
    return value;
  };
  useEffect(() => memo.current.clear(), [fires, places]);

  const buildRef = useRef<(minutes: number) => Layer[]>(() => []);
  const build = (minutes: number) => {
    const p = propsRef.current;
    const out: Layer[] = [];
    const t0ms = toMs(p.t0);
    const hourOffset = p.staticHour ?? minutes / 60 + H_MIN;
    const nowMs = t0ms + hourOffset * 3600_000;
    const surface = theme === "dark" ? [15, 17, 19] : [255, 255, 255];

    // 1. smoke field (bitmap), interpolated between hours
    field.setVisible(!!(p.layers.field && grid && frames));
    if (p.layers.field && grid && frames) {
      const pos = Math.max(0, Math.min(frames.length - 1, hourOffset - H_MIN));
      const q = p.reducedMotion || p.staticHour != null ? Math.round(pos) : Math.round(pos * 6) / 6;
      const key = `${theme}:${q}`;
      const canvas = cache.get(key, () => {
        const c = document.createElement("canvas");
        c.width = grid.nx;
        c.height = grid.ny;
        const ctx = c.getContext("2d")!;
        const img = ctx.createImageData(grid.nx, grid.ny);
        const i0 = Math.floor(q), i1 = Math.min(frames.length - 1, i0 + 1), f = q - i0;
        const a = frames[i0], b = frames[i1];
        for (let j = 0; j < grid.ny; j++) {
          const row = grid.ny - 1 - j; // row 0 = south -> bottom of the canvas
          for (let i = 0; i < grid.nx; i++) {
            const k = j * grid.nx + i;
            const v = Math.round(a[k] * (1 - f) + b[k] * f);
            const o = (row * grid.nx + i) * 4;
            img.data[o] = lut[v * 4];
            img.data[o + 1] = lut[v * 4 + 1];
            img.data[o + 2] = lut[v * 4 + 2];
            img.data[o + 3] = lut[v * 4 + 3] * edgeFade(i, j, grid.nx, grid.ny);
          }
        }
        ctx.putImageData(img, 0, 0);
        return c;
      });
      field.paint(key, canvas);
    }

    // 2. smoke trails
    // Dark: warm additive glow (overlapping strands brighten, like lit smoke).
    // Light: sepia ink at normal blending, so dense plumes read as darker, never as glare.
    if (p.layers.trails && tripRows && !p.reducedMotion && p.staticHour == null) {
      const dark = theme === "dark";
      const rgb = hexToRgb(dark ? TRAIL_COLOR.dark : TRAIL_COLOR.light);
      out.push(
        new TripsLayer({
          id: "smoke-trails",
          data: tripRows,
          getPath: (d: TripRow) => d.path,
          getTimestamps: (d: TripRow) => d.ts,
          getColor: [rgb[0], rgb[1], rgb[2]],
          opacity: dark ? 0.2 : 0.17,
          widthUnits: "pixels",
          getWidth: zoom >= 8 ? 2 : 1.35,
          widthMinPixels: 1,
          capRounded: true,
          jointRounded: true,
          fadeTrail: true,
          trailLength: 240,
          currentTime: minutes,
          pickable: false,
          parameters: dark
            ? { blend: true, blendColorOperation: "add", blendColorSrcFactor: "src-alpha", blendColorDstFactor: "one", blendAlphaOperation: "add", blendAlphaSrcFactor: "one", blendAlphaDstFactor: "one-minus-src-alpha" }
            : undefined,
          updateTriggers: { getWidth: zoom >= 8 },
        }),
      );
    }

    // 3. fires seen so far (observed detections only appear once detected)
    const fireColor = FIRE_COLOR[theme];
    const radius = (frp: number | null) => (frp == null ? 1400 : 500 + 190 * Math.sqrt(frp));
    if (p.layers.fires) {
      out.push(
        new ScatterplotLayer({
          id: "fires-midday",
          // fires appear once detected; re-filter only when the hour changes
          data: keep(`fm:${Math.floor(nowMs / 3600_000)}`, () => fireRows.filter((f) => !f.p.afternoon && f.ms <= nowMs)),
          getPosition: (d: (typeof fireRows)[number]) => [d.lon, d.lat],
          getRadius: (d: (typeof fireRows)[number]) => radius(d.p.frp_mw),
          radiusMinPixels: 2.2,
          radiusMaxPixels: 14,
          getFillColor: [...fireColor, 235],
          stroked: true,
          getLineColor: [...surface, 220] as [number, number, number, number],
          lineWidthMinPixels: 1,
          pickable: true,
          updateTriggers: { getFillColor: theme, getLineColor: theme },
        }),
      );
    }
    if (p.layers.missed) {
      const splitL = splitLon;
      out.push(
        new ScatterplotLayer({
          id: "fires-evening",
          data: keep(`fe:${Math.floor(nowMs / 3600_000)}:${splitL?.toFixed(3)}`, () =>
            fireRows.filter((f) => f.p.afternoon && f.ms <= nowMs && (splitL == null || f.lon >= splitL)),
          ),
          getPosition: (d: (typeof fireRows)[number]) => [d.lon, d.lat],
          getRadius: (d: (typeof fireRows)[number]) => radius(d.p.frp_mw) * 0.85,
          radiusMinPixels: 3.2,
          radiusMaxPixels: 15,
          filled: true,
          getFillColor: [...fireColor, 40] as [number, number, number, number],
          stroked: true,
          getLineColor: [...fireColor, 255] as [number, number, number, number],
          lineWidthMinPixels: 1.6,
          pickable: true,
          updateTriggers: { getFillColor: theme, getLineColor: theme },
        }),
      );
    }

    // 4. "across the border" note, anchored west of the cross-border fires
    if (p.borderLabel && zoom < 9.5) {
      const dark = theme === "dark";
      out.push(
        new TextLayer({
          id: "border-label",
          data: [p.borderLabel],
          getPosition: (d: { lon: number; lat: number }) => [d.lon, d.lat],
          getText: (d: { text: string }) => d.text,
          getSize: 11,
          lineHeight: 1.35,
          fontFamily: fontFamily(),
          fontWeight: 600,
          characterSet: "auto",
          // right edge on the anchor: the label always extends west, away from India
          getTextAnchor: "end",
          getAlignmentBaseline: "center",
          getColor: dark ? [239, 236, 228, 235] : [21, 23, 26, 230],
          background: true,
          getBackgroundColor: dark ? [21, 23, 27, 215] : [255, 255, 255, 225],
          getBorderColor: dark ? [70, 76, 86, 255] : [200, 199, 193, 255],
          getBorderWidth: 1,
          backgroundPadding: [7, 4, 7, 4],
          pickable: false,
          updateTriggers: { getColor: theme, getBackgroundColor: theme, getBorderColor: theme },
        }),
      );
    }

    // 5. highlighted cluster ring
    if (p.highlightCluster) {
      out.push(
        new ScatterplotLayer({
          id: "cluster-highlight",
          data: [p.highlightCluster],
          getPosition: (d: { lon: number; lat: number }) => [d.lon, d.lat],
          getRadius: 5000,
          radiusMinPixels: 14,
          filled: false,
          stroked: true,
          getLineColor: theme === "dark" ? [239, 236, 228, 255] : [21, 23, 26, 255],
          lineWidthMinPixels: 2,
        }),
      );
    }

    // 6. receptor pins (zoom-gated). Data arrays are reused between frames so deck.gl
    // doesn't rebuild attributes 60 times a second during playback.
    if (p.layers.places && places) {
      const zb = zoom >= 9.5 ? 3 : zoom >= 8.5 ? 2 : zoom >= 7 ? 1 : 0;
      const visible = keep(`places:${zb}:${p.selectedPlaceId}:${places.length}`, () =>
        places.filter((pl) => {
          if (pl.id === p.selectedPlaceId) return false; // drawn on its own layer below
          if (pl.arrival_utc) return zb >= 1 || pl.kind === "city" || pl.kind === "town";
          // no smoke expected: context only once zoomed in (the basemap already names cities)
          if (zb === 3) return true;
          if (zb === 2) return pl.kind === "city" || pl.kind === "town" || pl.kind === "ward";
          return false;
        }),
      );
      const ink = theme === "dark" ? [239, 236, 228] : [21, 23, 26];
      const smoke = hexToRgb(theme === "dark" ? SMOKE_RAMP.dark[4] : SMOKE_RAMP.light[2]);
      out.push(
        new ScatterplotLayer({
          id: "places",
          data: visible,
          getPosition: (d: PlaceIndexEntry) => [d.lon, d.lat],
          getRadius: (d: PlaceIndexEntry) => (d.arrival_utc ? (d.kind === "city" ? 4.5 : 3.75) : 2.75),
          radiusUnits: "pixels",
          getFillColor: (d: PlaceIndexEntry) =>
            d.arrival_utc ? [...smoke, 255] : [...(surface as [number, number, number]), 230],
          stroked: true,
          getLineColor: (d: PlaceIndexEntry) => [...ink, d.arrival_utc ? 255 : 150] as [number, number, number, number],
          getLineWidth: (d: PlaceIndexEntry) => (d.arrival_utc ? 1.25 : 1),
          lineWidthUnits: "pixels",
          pickable: true,
          autoHighlight: true,
          highlightColor: [...smoke, 255],
          updateTriggers: { getFillColor: theme, getLineColor: theme },
        }),
      );
      const sel = p.selectedPlaceId ? keep(`sel:${p.selectedPlaceId}:${places.length}`, () => places.filter((pl) => pl.id === p.selectedPlaceId)) : [];
      if (sel.length) {
        out.push(
          new ScatterplotLayer({
            id: "place-selected",
            data: sel,
            getPosition: (d: PlaceIndexEntry) => [d.lon, d.lat],
            getRadius: 7,
            radiusUnits: "pixels",
            getFillColor: [...smoke, 255],
            stroked: true,
            getLineColor: [...(surface as [number, number, number]), 255],
            getLineWidth: 2.5,
            lineWidthUnits: "pixels",
            pickable: true,
            updateTriggers: { getFillColor: theme, getLineColor: theme },
          }),
          new ScatterplotLayer({
            id: "place-selected-ring",
            data: sel,
            getPosition: (d: PlaceIndexEntry) => [d.lon, d.lat],
            getRadius: 12,
            radiusUnits: "pixels",
            filled: false,
            stroked: true,
            getLineColor: [...ink, 230] as [number, number, number, number],
            getLineWidth: 1.5,
            lineWidthUnits: "pixels",
            updateTriggers: { getLineColor: theme },
          }),
        );
      }
    }
    return out;
  };

  // keep the latest props/builder for the per-frame callback (assigned after render)
  useLayoutEffect(() => {
    propsRef.current = props;
    buildRef.current = build;
  });

  // create the deck overlay once the map exists
  useEffect(() => {
    if (!map) return;
    // Not interleaved: deck 9.4's interleaved mode reads maplibre<6 transform internals.
    // The smoke field is a maplibre canvas source instead (below the labels); see useFieldSource.
    const overlay = new MapboxOverlay({
      interleaved: false,
      layers: [],
      getCursor: ({ isHovering }) => (isHovering ? "pointer" : "grab"),
      onClick: (info: PickingInfo) => {
        if ((info.layer?.id === "places" || info.layer?.id === "place-selected") && info.object) propsRef.current.onPickPlace?.((info.object as PlaceIndexEntry).id);
      },
      getTooltip: (info: PickingInfo) => {
        if (!info.object) return null;
        const dark = document.documentElement.classList.contains("dark");
        const style = {
          background: dark ? "#15171b" : "#ffffff",
          color: dark ? "#efece4" : "#15171a",
          border: `1px solid ${dark ? "#262a30" : "#e4e3de"}`,
          borderRadius: "6px",
          padding: "6px 8px",
          fontSize: "12px",
          fontFamily: "var(--font-geist-sans), sans-serif",
          fontVariantNumeric: "tabular-nums",
          boxShadow: "0 4px 16px rgb(0 0 0 / 0.12)",
        };
        if (info.layer?.id === "places" || info.layer?.id === "place-selected") {
          const d = info.object as PlaceIndexEntry;
          return { html: `<strong>${escapeHtml(d.name)}</strong><br/><span style="opacity:.7">${escapeHtml(d.district)}</span>`, style };
        }
        if (info.layer?.id?.startsWith("fires")) {
          const d = info.object as { p: { sensor: string; acq_utc: string; frp_mw: number | null; confidence: string; afternoon: boolean } };
          const frp = d.p.frp_mw == null ? "FRP n/a" : `FRP ${d.p.frp_mw.toFixed(1)} MW`;
          const note = d.p.afternoon ? "<br/><span style=\"opacity:.7\">evening detection · lower confidence</span>" : "";
          return { html: `<strong>${escapeHtml(d.p.sensor)}</strong> · ${istTime(d.p.acq_utc)} IST<br/>${frp} · ${escapeHtml(d.p.confidence)}${note}`, style };
        }
        return null;
      },
    });
    map.addControl(overlay);
    overlayRef.current = overlay;
    overlay.setProps({ layers: buildRef.current(playback.get().minutes) });
    const off = playback.onFrame((m) => overlay.setProps({ layers: buildRef.current(m) }));
    return () => {
      off();
      try {
        map.removeControl(overlay);
      } catch {}
      overlayRef.current = null;
    };
  }, [map]);

  // re-render layers whenever inputs change
  useEffect(() => {
    overlayRef.current?.setProps({ layers: buildRef.current(playback.get().minutes) });
  });

  // fly to target
  const flyKey = props.flyTo?.key;
  useEffect(() => {
    const f = propsRef.current.flyTo;
    if (!map || !f || !isLoaded) return;
    const opts = { center: [f.lon, f.lat] as [number, number], zoom: f.zoom ?? Math.max(map.getZoom(), 8) };
    if (propsRef.current.reducedMotion) map.jumpTo(opts);
    else map.flyTo({ ...opts, duration: 1600, essential: true });
  }, [map, isLoaded, flyKey]);

  return null;
}

let cachedFont: string | null = null;
function fontFamily() {
  if (cachedFont) return cachedFont;
  if (typeof document === "undefined") return "monospace";
  // next/font registers a hashed family name; read it from the mono label style
  const probe = document.createElement("span");
  probe.className = "font-mono";
  document.body.appendChild(probe);
  cachedFont = getComputedStyle(probe).fontFamily || "monospace";
  probe.remove();
  return cachedFont;
}

function escapeHtml(s: string) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

export default function SmokeMap(props: SmokeMapProps) {
  const { resolvedTheme } = useTheme();
  const theme: ThemeName = resolvedTheme === "dark" ? "dark" : "light";
  const ink = theme === "dark" ? "#efece4" : "#15171a";
  return (
    <div className={props.className} role="region" aria-label={props.ariaLabel}>
      <MapView
        theme={theme}
        center={props.initialCenter ?? INITIAL_CENTER}
        zoom={props.initialZoom ?? 6.6}
        minZoom={4.5}
        maxZoom={13}
        dragRotate={false}
        pitchWithRotate={false}
        touchPitch={false}
        className="bg-surface-map"
      >
        <Overlay {...props} theme={theme} />
        {props.arcs && props.arcs.length > 0 && (
          <MapArc
            id="downwind-arcs"
            data={props.arcs}
            curvature={0.22}
            interactive={false}
            paint={{ "line-color": ink, "line-width": 1.6, "line-opacity": 0.75, "line-dasharray": [2, 1.5] }}
          />
        )}
        <MapControls position="top-right" showZoom showCompass={false} />
      </MapView>
    </div>
  );
}
