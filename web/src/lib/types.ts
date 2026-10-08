/**
 * Typed models for every Dhuaan artifact and API response.
 * Mirrors docs/CONTRACTS.md exactly. Optional fields marked "extension" are
 * proposals the UI tolerates being absent.
 */

/** UTC ISO-8601 timestamp with a Z suffix, e.g. "2026-10-08T06:00:00Z". */
export type UtcIso = string;

export type NaqiCategory = "good" | "satisfactory" | "moderate" | "poor" | "very_poor" | "severe";
export const NAQI_CATEGORIES: NaqiCategory[] = ["good", "satisfactory", "moderate", "poor", "very_poor", "severe"];

export type Sensor = "VIIRS_SNPP" | "VIIRS_NOAA20" | "VIIRS_NOAA21" | "MODIS" | "MSG_IODC" | "GK2A";
export type Confidence = "low" | "nominal" | "high";
export type PlaceKind = "village" | "town" | "city" | "school" | "ward";
export type Lang = "en" | "hi" | "pa";

// 1. fires.geojson
export interface FireProperties {
  id: string;
  sensor: Sensor;
  frp_mw: number | null;
  confidence: Confidence;
  acq_utc: UtcIso;
  cluster_id: string;
  /** true when local time is >= 15:00 IST */
  afternoon: boolean;
}
export interface FireFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: FireProperties;
}
export interface FiresGeoJSON {
  type: "FeatureCollection";
  features: FireFeature[];
}

// 2. clusters.json
export interface DownwindPlace {
  place_id: string;
  name: string;
  kind: PlaceKind;
  arrival_utc: UtcIso | null;
  peak_utc: UtcIso;
  peak_smoke: number;
}
export interface Cluster {
  cluster_id: string;
  lat: number;
  lon: number;
  n_detections: number;
  frp_sum_mw: number;
  first_seen_utc: UtcIso;
  last_seen_utc: UtcIso;
  district: string;
  state: string;
  nearest_place: string;
  rank: number;
  /** next 48 h */
  exposure_person_hours: number;
  /** 0-1 */
  exposure_share: number;
  /** top 5 by exposure contribution */
  downwind: DownwindPlace[];
}
export interface ClustersFile {
  t0_utc: UtcIso;
  clusters: Cluster[];
}

// 3. trips.json
export interface Trip {
  cluster_id: string;
  path: [number, number][];
  /** minutes since t0 - 24 h */
  ts: number[];
}
export interface TripsFile {
  t0_utc: UtcIso;
  step_minutes: number;
  trips: Trip[];
}

// 4. grid.json
export interface GridFile {
  lon0: number;
  lat0: number;
  dlon: number;
  dlat: number;
  nx: number;
  ny: number;
  t0_utc: UtcIso;
  hours: number;
  scale: number;
  /** base64 uint8 (ny*nx row-major, row 0 = south); value = round(255 * min(1, smoke/scale)) */
  frames: string[];
}

// 5. receptors_index.json
export interface PlaceIndexEntry {
  id: string;
  name: string;
  kind: PlaceKind;
  district: string;
  state: string;
  lat: number;
  lon: number;
  peak_smoke: number;
  peak_utc: UtcIso;
  arrival_utc: UtcIso | null;
}
export interface ReceptorsIndex {
  t0_utc: UtcIso;
  places: PlaceIndexEntry[];
}

// 6. places/<id>.json
export interface Attribution {
  district: string;
  state: string;
  share: number;
}
/** extension (not in CONTRACTS yet): latest monitor reading near the place */
export interface AqNow {
  station: string;
  provider?: string;
  pm25: number;
  category: NaqiCategory;
  obs_utc: UtcIso;
}
export interface PlaceDetail {
  id: string;
  name: string;
  kind: PlaceKind;
  district: string;
  state: string;
  lat: number;
  lon: number;
  t0_utc: UtcIso;
  /** 97 floats: ensemble median, index 0 = t0 - 24 h */
  series: number[];
  p10: number[];
  p90: number[];
  arrival_utc: UtcIso | null;
  arrival_window: [UtcIso, UtcIso] | null;
  peak_utc: UtcIso;
  peak_smoke: number;
  /** t0 -> t0 + 48 h, top 5 plus {district: "Other"} */
  attribution: Attribution[];
  top_clusters: { cluster_id: string; share: number }[];
  aq_now?: AqNow | null;
}

// 7. meta.json
export interface SourceStatus {
  name: string;
  fetched_utc: UtcIso;
  latest_obs_utc: UtcIso | null;
  count: number;
  ok: boolean;
  note: string;
}
export interface Meta {
  run_id: string;
  t0_utc: UtcIso;
  generated_utc: UtcIso;
  model_version: string;
  members: number;
  afternoon_mode: "none" | "estimated" | "observed";
  alpha: number;
  calibrated: boolean;
  arrival_threshold: number;
  scale: number;
  domain: unknown;
  sources: SourceStatus[];
  /** present and true on fixture data */
  synthetic?: boolean;
}

// 8. advisories/<school_id>.json
export type OutdoorAdvice = "ok" | "limit" | "indoors";
export interface AdvisoryHour {
  hour_ist: number;
  est_pm25: number;
  category: NaqiCategory;
  outdoor: OutdoorAdvice;
}
export interface Advisory {
  school_id: string;
  date_ist: string;
  plan: AdvisoryHour[];
  notice: { en: string; hi: string; pa: string };
  grounding: { verified: number; total: number };
  model: string;
}

// 9. backtest.json
export interface BacktestPoint {
  t: UtcIso;
  obs_excess: number | null;
  pred_A: number | null;
  pred_B: number | null;
}
export interface BacktestStation {
  id: string;
  name: string;
  lat: number;
  lon: number;
  series: BacktestPoint[];
}
export type BacktestMetrics = Record<string, number | string | null>;
export interface Backtest {
  window: unknown;
  met_source: string;
  stations: BacktestStation[];
  metrics: { A: BacktestMetrics; B: BacktestMetrics };
  calibration: { alpha_A: number; alpha_B: number };
  notes: string | string[];
}

// API
export interface HealthResponse {
  ok: boolean;
  run_id: string;
  model_provider: string;
}
export interface SearchResponse {
  places: PlaceIndexEntry[];
}
export interface AskRequest {
  question: string;
  place_id?: string;
  lang: Lang;
}
export interface ToolTraceEntry {
  tool: string;
  args: Record<string, unknown>;
  summary: string;
}
export interface AskResponse {
  answer: string;
  lang: Lang;
  tool_trace: ToolTraceEntry[];
  grounding: { verified: number; total: number; unverified: string[] };
  model: string;
  cached: boolean;
}
