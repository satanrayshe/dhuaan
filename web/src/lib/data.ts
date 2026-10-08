"use client";

import { useSyncExternalStore } from "react";
import type {
  Advisory,
  AskRequest,
  AskResponse,
  Backtest,
  ClustersFile,
  FiresGeoJSON,
  GridFile,
  HealthResponse,
  Meta,
  PlaceDetail,
  ReceptorsIndex,
  TripsFile,
} from "./types";

export const DATA_BASE = (process.env.NEXT_PUBLIC_DATA_BASE ?? "/data").replace(/\/$/, "");
export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8787").replace(/\/$/, "");

export const artifactUrl = (name: string) => `${DATA_BASE}/latest/${name}`;

export type Resource<T> =
  | { status: "idle"; data?: undefined; error?: undefined }
  | { status: "loading"; data?: undefined; error?: undefined }
  | { status: "ready"; data: T; error?: undefined }
  | { status: "missing"; data?: undefined; error?: undefined }
  | { status: "error"; data?: undefined; error: string };

const IDLE: Resource<never> = { status: "idle" };
const LOADING: Resource<never> = { status: "loading" };

const entries = new Map<string, Resource<unknown>>();
const listeners = new Map<string, Set<() => void>>();

function notify(url: string) {
  listeners.get(url)?.forEach((l) => l());
}

async function fetchJson<T>(url: string, init?: RequestInit, timeoutMs = 20000): Promise<T> {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { ...init, signal: ctl.signal });
    if (!res.ok) {
      const err = new Error(`HTTP ${res.status}`) as Error & { status?: number };
      err.status = res.status;
      throw err;
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

function load(url: string) {
  const cur = entries.get(url);
  if (cur && cur.status !== "error") return;
  entries.set(url, LOADING);
  fetchJson<unknown>(url, { cache: "no-cache" })
    .then((data) => entries.set(url, { status: "ready", data }))
    .catch((e: Error & { status?: number }) => {
      // a missing artifact is a normal state (e.g. backtest pending), not an error
      if (e.status === 404 || e.status === 403) entries.set(url, { status: "missing" });
      else entries.set(url, { status: "error", error: e.message || "network error" });
    })
    .finally(() => notify(url));
}

/** Re-fetch a resource (used by retry buttons). */
export function reload(url: string) {
  entries.delete(url);
  load(url);
  notify(url);
}

export function useResource<T>(url: string | null): Resource<T> {
  return useSyncExternalStore(
    (cb) => {
      if (!url) return () => {};
      let set = listeners.get(url);
      if (!set) listeners.set(url, (set = new Set()));
      set.add(cb);
      load(url);
      return () => set!.delete(cb);
    },
    () => (url ? ((entries.get(url) as Resource<T>) ?? LOADING) : IDLE),
    () => (url ? LOADING : IDLE),
  );
}

export const useMeta = () => useResource<Meta>(artifactUrl("meta.json"));
export const useFires = () => useResource<FiresGeoJSON>(artifactUrl("fires.geojson"));
export const useClusters = () => useResource<ClustersFile>(artifactUrl("clusters.json"));
export const useTrips = (enabled = true) => useResource<TripsFile>(enabled ? artifactUrl("trips.json") : null);
export const useGrid = () => useResource<GridFile>(artifactUrl("grid.json"));
export const useReceptors = () => useResource<ReceptorsIndex>(artifactUrl("receptors_index.json"));
export const usePlace = (id: string | null | undefined) =>
  useResource<PlaceDetail>(id ? artifactUrl(`places/${encodeURIComponent(id)}.json`) : null);
export const useAdvisoryArtifact = (schoolId: string | null | undefined) =>
  useResource<Advisory>(schoolId ? artifactUrl(`advisories/${encodeURIComponent(schoolId)}.json`) : null);
export const useBacktest = () => useResource<Backtest>(artifactUrl("backtest.json"));
export const useHealth = () => useResource<HealthResponse>(`${API_BASE}/api/health`);

export async function ask(body: AskRequest): Promise<AskResponse> {
  return fetchJson<AskResponse>(
    `${API_BASE}/api/ask`,
    { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) },
    60000,
  );
}

/** Stale when the run is older than 6 h (pipeline runs every 3 h). */
export function isStale(meta: Meta | undefined, now = Date.now()): boolean {
  if (!meta) return false;
  return now - Date.parse(meta.generated_utc) > 6 * 3600_000;
}
