import { useSyncExternalStore } from "react";
import type { Cluster, FiresGeoJSON } from "./types";

export function useMediaQuery(q: string, serverValue = false): boolean {
  return useSyncExternalStore(
    (cb) => {
      const mq = window.matchMedia(q);
      mq.addEventListener("change", cb);
      return () => mq.removeEventListener("change", cb);
    },
    () => window.matchMedia(q).matches,
    () => serverValue,
  );
}

const GEO = new Set(["MSG_IODC", "GK2A"]);

/** Evening detections from a geostationary sensor exist in this run (never fake the layer). */
export function hasEveningLayer(fires?: FiresGeoJSON): boolean {
  return !!fires?.features.some((f) => f.properties.afternoon && GEO.has(f.properties.sensor));
}

/**
 * Detections after 15:00 IST from geostationary sensors whose cluster has no
 * midday (polar-orbiter) detection, i.e. fires the midday pass did not see.
 */
export function missedByMidday(fires?: FiresGeoJSON): number {
  if (!fires) return 0;
  const midday = new Set<string>();
  for (const f of fires.features) if (!f.properties.afternoon) midday.add(f.properties.cluster_id);
  let n = 0;
  for (const f of fires.features)
    if (f.properties.afternoon && GEO.has(f.properties.sensor) && !midday.has(f.properties.cluster_id)) n++;
  return n;
}

/** Smallest k of top-ranked clusters reaching >= target share of exposure. */
export function headlineStat(clusters: Cluster[], target = 0.6) {
  const sorted = [...clusters].sort((a, b) => b.exposure_share - a.exposure_share);
  const total = sorted.reduce((a, c) => a + c.exposure_share, 0) || 1;
  let cum = 0;
  let k = 0;
  for (const c of sorted) {
    cum += c.exposure_share;
    k++;
    if (cum / total >= target) break;
  }
  return { k, n: sorted.length, pct: Math.round((cum / total) * 100), detections: sorted.reduce((a, c) => a + c.n_detections, 0) };
}
