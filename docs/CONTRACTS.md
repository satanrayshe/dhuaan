# Dhuaan contracts (source of truth for every component)

Every component codes against this file. If you need to change a contract, don't change it silently: write the change in your final report.

## Repo layout and ownership
```
backend/                       Python 3.12 package `dhuaan` (uv project; deps fixed in pyproject.toml, don't edit it)
  dhuaan/config.py             env + paths (owner: integration)
  dhuaan/model/                smoke model (owner: MODEL)
  dhuaan/ingest/               FIRMS, Open-Meteo, LSA SAF, OpenAQ clients (owner: INGEST)
  dhuaan/geo/                  districts lookup, receptors + population loaders (owner: INGEST)
  dhuaan/pipeline/             run_local, Lambda handlers for ingest/model/score/advise (owner: INGEST)
  dhuaan/agent/                Strands agent, tools, rules, grounding (owner: AGENT)
  dhuaan/api/                  Lambda Function URL handler (owner: AGENT)
  dhuaan/store.py              artifact store: local dir or S3 (owner: AGENT; INGEST uses it)
  dhuaan/backtest/             phase 2
  data/                        small static data committed to git (owner: INGEST)
  tests/<component>/           pytest per component
infra/                         SAM template, layer build scripts, deploy scripts (owner: INFRA)
web/                           Next.js static-export app (owner: WEB)
docs/                          CONTRACTS, PROGRESS, what-fought-back, architecture
```
Rules for every agent:
- Write only inside the paths you own.
- **Never run git.**
- Never print secrets from `.env`.
- Use `uv run` from `backend/` (the venv is already synced).
- Python 3.12 with type hints, small modules, no heavy frameworks.

## Domain, time, units
- **Domain:** lon 72.5 → 79.0, lat 28.0 → 32.75 (Punjab, Haryana, Delhi/NCR, west UP, north Rajasthan).
- **Met grid:** 0.25° (27 × 20 = 540 points). **Output grid:** 0.1° (66 × 48 cells; cell centres at lon0 + (i+0.5)·0.1).
- **Time:** all timestamps are **UTC ISO-8601 with a `Z` suffix** (`2026-10-08T06:00:00Z`). The UI converts to IST (UTC+5:30).
  - `t0` is the run start: the model run time floored to the hour.
  - The run covers t0−24 h → t0+72 h hourly. That's **97 hours, indexed −24 … +72**; arrays are stored in order, with index 0 = t0−24 h.
- **Smoke index:** the model's relative concentration ("smoke units").
  - `est_pm25 = alpha × smoke_index` in µg/m³, labelled everywhere as **"est. smoke PM2.5 (provisional calibration)"**. `alpha` comes from the backtest calibration (default `alpha = 1.0` until calibrated; `meta.calibrated=false`).
  - **Region-appropriate alpha:** `meta.alpha_by_region[region_of(district, state)]`, falling back to `meta.alpha`. Regions live in one helper, `backend/dhuaan/geo/regions.py`, mirrored in `web/src/lib/regions.ts` (keep the NCR list identical): `delhi_ncr` = Delhi + Gurgaon/Gurugram, Faridabad, Sonipat, Jhajjar, Palwal, Ghaziabad, Gautam Buddha Nagar, Baghpat; `punjab_haryana` = the rest of Punjab, Haryana, Chandigarh; `_default` = everything else.
- **NAQI categories (PM2.5 µg/m³):** good ≤30 · satisfactory 31–60 · moderate 61–90 · poor 91–120 · very_poor 121–250 · severe >250. The keys are exactly those snake_case strings.

## In-memory types (dhuaan/model/types.py, owned by MODEL, imported by everyone)
```python
@dataclass(frozen=True)
class Fire:            # one satellite detection
    id: str; lat: float; lon: float; time_utc: datetime  # tz-aware UTC
    frp_mw: float | None          # None for sources without FRP (e.g. GK2A)
    sensor: str                   # "VIIRS_SNPP"|"VIIRS_NOAA20"|"VIIRS_NOAA21"|"MODIS"|"MSG_IODC"|"GK2A"
    confidence: str               # "low"|"nominal"|"high"

@dataclass
class MetField:        # hourly, regular grid
    lons: np.ndarray  # (nx,)  ascending
    lats: np.ndarray  # (ny,)  ascending
    times: list[datetime]  # (nt,) hourly UTC
    u10: np.ndarray; v10: np.ndarray; u925: np.ndarray; v925: np.ndarray
    u850: np.ndarray; v850: np.ndarray      # m/s, shape (nt, ny, nx)
    blh: np.ndarray                          # boundary layer height m, (nt, ny, nx)

@dataclass(frozen=True)
class Receptor:
    id: str; name: str; kind: str   # "village"|"town"|"city"|"school"|"ward"
    district: str; state: str; lat: float; lon: float
    population: int | None
```
`model.run(fires, met, receptors, population_grid, t0, *, members=5, seed=0, afternoon_mode="none"|"estimated"|"observed", district_of=callable(lat, lon)->(district, state)) -> dict[str, Any]` returns the artifact dict: `filename → JSON-serialisable object`, exactly the files below except `meta.json`, which the pipeline adds.

## Artifacts (S3 `s3://<bucket>/latest/…` and `runs/<run_id>/…`; locally `backend/out/latest/`; web reads `/data/latest/…`)
1. **`fires.geojson`**: FeatureCollection of Points.
   - properties: `{id, sensor, frp_mw, confidence, acq_utc, cluster_id, afternoon}`
   - `afternoon` is true when the local time is ≥ 15:00 IST.
2. **`clusters.json`**: `{t0_utc, clusters: [...]}`, sorted by rank. Each cluster:
   - `cluster_id, lat, lon, n_detections, frp_sum_mw, first_seen_utc, last_seen_utc, district, state, nearest_place, rank`
   - `exposure_person_hours` (next 48 h) and `exposure_share` (0–1)
   - `downwind: [{place_id, name, kind, arrival_utc|null, peak_utc, peak_smoke}]` (top 5 by exposure contribution)
3. **`trips.json`**: `{t0_utc, step_minutes, trips: [{cluster_id, path: [[lon,lat],...], ts: [minutes since t0−24h,...]}]}`
   - At most 3,000 trips; `step_minutes` = 60 (the web interpolates between points); coordinates rounded to 3 dp (~100 m).
   - This is the deck.gl `TripsLayer` input.
4. **`grid.json`**: `{lon0, lat0, dlon, dlat, nx, ny, t0_utc, hours: 97, scale, frames: [base64 uint8 (ny*nx row-major, row 0 = south)], blh_m?}`
   - value = round(255 · min(1, smoke/scale)); `scale` is the 99th-percentile smoke over the run.
   - `blh_m` (optional): 97 integers, the hourly domain-mean boundary-layer height in metres (index 0 = t0−24 h), for the web time scrubber. Absent if it could not be computed.
5. **`receptors_index.json`**: `{t0_utc, places: [{id, name, kind, district, state, lat, lon, peak_smoke, peak_utc, arrival_utc|null}]}`
   - Used for search and map pins; keep it under about 1.5 MB.
6. **`places/<id>.json`**: `{id, name, kind, district, state, lat, lon, t0_utc, series: [97 floats, 2 dp], p10: [97], p90: [97], arrival_utc|null, arrival_window: [earliest_utc, latest_utc]|null, peak_utc, peak_smoke, attribution: [{district, state, share}], top_clusters: [{cluster_id, share}]}`
   - `series` is the ensemble median; `p10`/`p90` give the band across members.
   - `attribution` covers t0 → t0+48 h, with the top 5 plus `{district:"Other"}`.
   - **Arrival** = first hour ≥ t0 when `series ≥ arrival_threshold` (in `meta`; default 0.15 × scale), or null.
7. **`meta.json`** (pipeline):
   - `{run_id, t0_utc, generated_utc, model_version, members, afternoon_mode, alpha, alpha_by_region, calibration_basis, calibrated, arrival_threshold, scale, domain, model_summary}`
   - `alpha` = the pooled, pre-registered backtest alpha (`alpha_B` when afternoon fires are used, else `alpha_A`); kept for backward compatibility.
   - `alpha_by_region: {delhi_ncr, punjab_haryana, _default}`: the exploratory regional alphas from `backtest.json.exploratory_regional.alphas[B|A]`; `_default` (and any missing region) = `alpha`. With `DHUAAN_ALPHA` set or no calibration, every region gets `alpha`.
   - `calibration_basis`: one human-readable sentence saying which alphas are used and that they are provisional.
   - `sources: [{name, fetched_utc, latest_obs_utc, count, ok, note}]`. For FIRMS, `count` is **after** static-hotspot masking; the note says how many were masked.
8. **`advisories/<school_id>.json`** (AGENT, phase 2):
   - `{school_id, name, district, date_ist, plan: [{hour_ist: "HH:MM" (IST string, e.g. "07:00"), est_pm25, est_pm25_low, est_pm25_high, category, outdoor: "ok"|"limit"|"indoors"}]}`; hours 07:00-13:00 IST.
   - `est_pm25 = baseline + alpha_region × smoke`; `est_pm25_low/high` use the ensemble p10/p90 at that hour. When low == high the notices omit the range (a "range 60-60" never appears).
   - Baseline: the nearest station's latest PM2.5 (OpenAQ, ≤ 50 km) if it is **≤ 36 h old** (CPCB data reach OpenAQ ~20 h late), else 60 µg/m³. Fields: `baseline_pm25, baseline_source: "measured"|"default", baseline_basis` (e.g. "measured 21 h ago at Patiala, 33 km" or "no recent nearby reading; default 60 ug/m3"), `baseline_age_h, baseline_station, baseline_distance_km`, plus `alpha, alpha_region, est_label`.
   - `summary, notice: {en, hi, pa}, notice_source, grounding: {verified, total, by_lang}, model, run_id, generated_utc, run_t0_ist, caveats, sources`
9. **`backtest.json`** (phase 2): `{window, met_source, stations: [{id, name, lat, lon, region, completeness, metrics: {A, B}, series: [{t, obs_excess, pred_A, pred_B}]}], metrics: {A: {...}, B: {...}}, calibration: {alpha_A, alpha_B, method}, notes}`
   - `metrics.A|B`: `{hit_rate, false_alarm_ratio, median_lead_h, pearson_r, r2, n_episodes, n_hits, episodes, hits, n_forecast_episodes, n_false_alarms, n_lead_episodes}` (counts are shown inside the hit-rate tile on the web, never as tiles).
   - Extra keys: `secondary_lead_0_23h: {A, B}` (same-day lead, not pre-registered), `excluded_stations: [{id, name, completeness}]`, `members`, `generated_utc`, `facts: {afternoon_share_2025, n_detections, source}`, `window.{fit, held_out, issue_times, scored_lead_h, episode_date}`.
   - **The pooled `calibration` + `metrics` are THE pre-registered result.**
   - `exploratory_regional` (**not pre-registered**): `{label: "Exploratory - not pre-registered", regions, alphas: {A: {delhi_ncr, punjab_haryana}, B: {...}}, metrics: {A, B}, by_region: {delhi_ncr: {A, B}, punjab_haryana: {A, B}}, n_stations, notes}`. One alpha per region fitted on the fit period only (25 Oct-5 Nov), scored on 6-20 Nov with the same metric code and the saved forecasts (`--reuse`). `by_region` also carries `share_hours_obs_ge60` / `share_hours_pred_ge60` (base rates for reading the hit rate).
10. **`baselines.json`** (AGENT, written by the advisory step): `{run_id, generated_utc, max_age_h: 36, default_pm25: 60, places: {<place_id>: {pm25, source, basis, age_h, station, distance_km, measured_utc, alpha, alpha_region}}}` for the advised schools and the demo places (data/demo_places.json). The web place card and schools page show the baseline text from it.

## API (one Lambda behind a Function URL; local dev at `http://localhost:8787`)
- `GET /api/health` → `{ok, run_id, model_provider}`
- `GET /api/search?q=<text>&limit=10` → `{places: [index entries]}`
- `POST /api/ask` with `{question, place_id?, lang: "en"|"hi"|"pa"}` → `{answer, lang, tool_trace: [{tool, args, summary}], grounding: {verified, total, unverified: [str]}, model, cached}`
- `GET /api/advisory?school_id=<id>&lang=en` → the advisory artifact
- CORS: allow the web origin (env `ALLOWED_ORIGIN`; `*` locally). Rate limits: 20 asks per IP per hour and 500 per day globally (DynamoDB counter in AWS; in memory locally).

## Environment (.env at repo root; Lambda reads SSM `/dhuaan/*`)
`FIRMS_MAP_KEY, OPENAQ_API_KEY, GEMINI_API_KEY, DATA_GOV_IN_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, LSASAF_USERNAME, LSASAF_PASSWORD`, plus non-secret settings:
- `MODEL_PROVIDER=gemini|bedrock`
- `GEMINI_MODEL=gemini-flash-lite-latest`
- `BEDROCK_MODEL_ID=global.amazon.nova-2-lite-v1:0`
- `AWS_REGION=ap-south-1`
- `ARTIFACT_STORE=local|s3`
- `ARTIFACT_BUCKET`
- `LOCAL_OUT=backend/out`
