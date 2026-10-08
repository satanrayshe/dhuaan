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
  - `est_pm25 = alpha × smoke_index` in µg/m³. `alpha` comes from the backtest calibration (default `alpha = 1.0` until calibrated; `meta.calibrated=false`).
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
   - At most 6,000 trips; coordinates rounded to 4 dp.
   - This is the deck.gl `TripsLayer` input.
4. **`grid.json`**: `{lon0, lat0, dlon, dlat, nx, ny, t0_utc, hours: 97, scale, frames: [base64 uint8 (ny*nx row-major, row 0 = south)]}`
   - value = round(255 · min(1, smoke/scale)); `scale` is the 99th-percentile smoke over the run.
5. **`receptors_index.json`**: `{t0_utc, places: [{id, name, kind, district, state, lat, lon, peak_smoke, peak_utc, arrival_utc|null}]}`
   - Used for search and map pins; keep it under about 1.5 MB.
6. **`places/<id>.json`**: `{id, name, kind, district, state, lat, lon, t0_utc, series: [97 floats, 2 dp], p10: [97], p90: [97], arrival_utc|null, arrival_window: [earliest_utc, latest_utc]|null, peak_utc, peak_smoke, attribution: [{district, state, share}], top_clusters: [{cluster_id, share}]}`
   - `series` is the ensemble median; `p10`/`p90` give the band across members.
   - `attribution` covers t0 → t0+48 h, with the top 5 plus `{district:"Other"}`.
   - **Arrival** = first hour ≥ t0 when `series ≥ arrival_threshold` (in `meta`; default 0.15 × scale), or null.
7. **`meta.json`** (pipeline):
   - `{run_id, t0_utc, generated_utc, model_version, members, afternoon_mode, alpha, calibrated, arrival_threshold, scale, domain}`
   - `sources: [{name, fetched_utc, latest_obs_utc, count, ok, note}]`
8. **`advisories/<school_id>.json`** (AGENT, phase 2):
   - `{school_id, date_ist, plan: [{hour_ist, est_pm25, category, outdoor: "ok"|"limit"|"indoors"}]}`
   - `notice: {en, hi, pa}`, `grounding: {verified, total}`, `model`
9. **`backtest.json`** (phase 2): `{window, met_source, stations: [{id, name, lat, lon, series: [{t, obs_excess, pred_A, pred_B}]}], metrics: {A: {...}, B: {...}}, calibration: {alpha_A, alpha_B}, notes}`

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
