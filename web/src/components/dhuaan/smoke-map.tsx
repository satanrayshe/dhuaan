"use client";

import { MapboxOverlay } from "@deck.gl/mapbox";
import { COORDINATE_SYSTEM, type Layer, type PickingInfo } from "@deck.gl/core";
import { BitmapLayer, ScatterplotLayer } from "@deck.gl/layers";
import { TripsLayer } from "@deck.gl/geo-layers";
import { useTheme } from "next-themes";
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Map as MapView, MapArc, MapControls, useMap, type MapArcDatum } from "@/components/ui/map";
import { FIRE_COLOR, SMOKE_RAMP, hexToRgb, smokeLut, type ThemeName } from "@/lib/colors";
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
  className?: string;
  /** show smoke at a fixed hour instead of following playback (district view) */
  staticHour?: number | null;
  ariaLabel: string;
}

const INITIAL_CENTER: [number, number] = [76.0, 29.95];

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

function Overlay(props: SmokeMapProps & { theme: ThemeName }) {
  const { map, isLoaded } = useMap();
  const overlayRef = useRef<MapboxOverlay | null>(null);
  const propsRef = useRef(props);
  const [zoom, setZoom] = useState(6.5);
  const [splitLon, setSplitLon] = useState<number | null>(null);

  const { fires, grid, trips, places, theme, splitAt } = props;

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

  const buildRef = useRef<(minutes: number) => Layer[]>(() => []);
  const build = (minutes: number) => {
    const p = propsRef.current;
    const out: Layer[] = [];
    const t0ms = toMs(p.t0);
    const hourOffset = p.staticHour ?? minutes / 60 + H_MIN;
    const nowMs = t0ms + hourOffset * 3600_000;
    const surface = theme === "dark" ? [15, 17, 19] : [255, 255, 255];

    // 1. smoke field (bitmap), interpolated between hours
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
            img.data[o + 3] = lut[v * 4 + 3];
          }
        }
        ctx.putImageData(img, 0, 0);
        return c;
      });
      out.push(
        new BitmapLayer({
          id: "smoke-field",
          image: canvas,
          bounds: [grid.lon0, grid.lat0, grid.lon0 + grid.nx * grid.dlon, grid.lat0 + grid.ny * grid.dlat],
          _imageCoordinateSystem: COORDINATE_SYSTEM.LNGLAT,
          textureParameters: { minFilter: "linear", magFilter: "linear" },
          opacity: 1,
          pickable: false,
        }),
      );
    }

    // 2. smoke trails
    if (p.layers.trails && trips && !p.reducedMotion && p.staticHour == null) {
      const rgb = hexToRgb(theme === "dark" ? SMOKE_RAMP.dark[5] : SMOKE_RAMP.light[2]);
      out.push(
        new TripsLayer({
          id: "smoke-trails",
          data: trips.trips,
          getPath: (d: TripsFile["trips"][number]) => d.path,
          getTimestamps: (d: TripsFile["trips"][number]) => d.ts,
          getColor: [rgb[0], rgb[1], rgb[2]],
          opacity: theme === "dark" ? 0.4 : 0.38,
          widthMinPixels: 1,
          widthMaxPixels: 2,
          getWidth: 600,
          capRounded: true,
          jointRounded: true,
          fadeTrail: true,
          trailLength: 180,
          currentTime: minutes,
          pickable: false,
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
          data: fireRows.filter((f) => !f.p.afternoon && f.ms <= nowMs),
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
          data: fireRows.filter((f) => f.p.afternoon && f.ms <= nowMs && (splitL == null || f.lon >= splitL)),
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

    // 4. highlighted cluster ring
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

    // 5. receptor pins (zoom-gated)
    if (p.layers.places && places) {
      const visible = places.filter((pl) => {
        if (pl.id === p.selectedPlaceId) return true;
        if (pl.kind === "city") return zoom >= 6.5;
        if (pl.kind === "ward" || pl.kind === "town") return zoom >= 7.75;
        return zoom >= 8.75;
      });
      const ink = theme === "dark" ? [239, 236, 228] : [21, 23, 26];
      const smoke = hexToRgb(theme === "dark" ? SMOKE_RAMP.dark[4] : SMOKE_RAMP.light[2]);
      out.push(
        new ScatterplotLayer({
          id: "places",
          data: visible,
          getPosition: (d: PlaceIndexEntry) => [d.lon, d.lat],
          getRadius: (d: PlaceIndexEntry) => (d.id === p.selectedPlaceId ? 9 : d.kind === "city" ? 5 : 4),
          radiusUnits: "pixels",
          getFillColor: (d: PlaceIndexEntry) =>
            d.id === p.selectedPlaceId ? [...smoke, 255] : [...(surface as [number, number, number]), 255],
          stroked: true,
          getLineColor: [...ink, 255] as [number, number, number, number],
          getLineWidth: (d: PlaceIndexEntry) => (d.id === p.selectedPlaceId ? 2.5 : 1.5),
          lineWidthUnits: "pixels",
          pickable: true,
          autoHighlight: true,
          highlightColor: [...smoke, 255],
          updateTriggers: {
            getRadius: p.selectedPlaceId,
            getFillColor: [p.selectedPlaceId, theme],
            getLineWidth: p.selectedPlaceId,
            getLineColor: theme,
          },
        }),
      );
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
    const overlay = new MapboxOverlay({
      interleaved: false,
      layers: [],
      getCursor: ({ isHovering }) => (isHovering ? "pointer" : "grab"),
      onClick: (info: PickingInfo) => {
        if (info.layer?.id === "places" && info.object) propsRef.current.onPickPlace?.((info.object as PlaceIndexEntry).id);
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
        if (info.layer?.id === "places") {
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
        center={INITIAL_CENTER}
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
