# Data sources, licences and attribution

Everything Dhuaan ingests or ships, with the credit line to show in the README / About page.
Static files in this folder are rebuilt with the commands listed (run from `backend/`).

| Dataset | Used for | Licence | Attribution text |
|---|---|---|---|
| NASA FIRMS active fires: VIIRS S-NPP, NOAA-20, NOAA-21 (375 m) and MODIS (1 km) NRT; SP for the archive | Live and backtest fire detections (`dhuaan/ingest/firms.py`) | NASA open data (no restrictions; citation requested) | "We acknowledge the use of data and/or imagery from NASA's Fire Information for Resource Management System (FIRMS) (https://earthdata.nasa.gov/firms), part of NASA's Earth Science Data and Information System (ESDIS)." |
| LSA SAF Meteosat IODC FRP-PIXEL (MSG, 15 min) | Live afternoon fires with FRP (`dhuaan/ingest/lsasaf.py`) | EUMETSAT LSA SAF data policy: free for non-commercial and research use with a registered account; credit required | "Contains modified EUMETSAT LSA SAF data [2026], FRP-PIXEL product (Wooster et al.), IPMA." |
| Open-Meteo Forecast API and Historical Forecast API | Winds at 10 m / 925 / 850 hPa and boundary-layer height (`dhuaan/ingest/openmeteo.py`) | CC BY 4.0 (free tier, non-commercial) | "Weather data by Open-Meteo.com (CC BY 4.0)", linking to https://open-meteo.com/ |
| OpenAQ v3 API and OpenAQ AWS archive (`s3://openaq-data-archive`) | Live PM2.5 near a place; backtest observations (`dhuaan/ingest/openaq.py`, `aq_stations.json`) | OpenAQ platform CC BY 4.0; underlying data under each provider's terms (CPCB, DPCC, PPCB, HSPCB and others; low-cost networks such as AirGradient) | "Air-quality data from OpenAQ (openaq.org), originally from CPCB/state pollution control boards and other providers listed per station." |
| Meta / CIESIN High Resolution Settlement Layer (HRSL) v1.5.2, AWS Open Data `s3://dataforgood-fb-data/hrsl-cogs/` | Population per 0.1 deg cell (`population_0p1.json`) | CC BY 4.0 | "Facebook Connectivity Lab and Center for International Earth Science Information Network (CIESIN), Columbia University. 2016. High Resolution Settlement Layer (HRSL). Source imagery for HRSL (c) 2016 DigitalGlobe. Accessed via the AWS Open Data Registry." |
| geoBoundaries IND ADM2 (2021, LGD-based; source Pathways Data Pvt. Ltd. / lgdirectory.gov.in) | District lookup (`districts.geojson`) | ODbL 1.0 | "District boundaries: geoBoundaries (Runfola et al. 2020, PLoS ONE 15(4): e0231866), IND ADM2 from Pathways Data / LGD, ODbL 1.0." |
| geoBoundaries IND ADM1 (source DataMeet, Election Commission of India) | State names for districts (build time only) | CC BY 2.5 IN | "State boundaries: DataMeet India community via geoBoundaries, CC BY 2.5 IN." |
| geoBoundaries PAK ADM1 / ADM2 (2019) | Districts for cross-border fires west of 75E (`districts.geojson`) | Public domain | "Pakistan boundaries: geoBoundaries (public domain)." |
| GeoNames `IN.zip` | Villages, towns and cities (`receptors.json`) | CC BY 4.0 | "Place names and populations: GeoNames (geonames.org), CC BY 4.0." |
| OpenStreetMap `amenity=school` via the Overpass API | School receptors (`receptors.json`, `demo_places.json`) | ODbL 1.0 | "(c) OpenStreetMap contributors, ODbL 1.0 (openstreetmap.org/copyright)." |
| datameet Municipal_Spatial_Data `Delhi/Delhi_Wards.geojson` | Delhi ward centroids, **pre-2022 boundaries (290 wards, before the 2022 MCD unification)** | CC BY-SA 2.5 IN | "Delhi ward boundaries (pre-2022): DataMeet Municipal Spatial Data, CC BY-SA 2.5 IN." Derived ward centroids are shared under the same licence. |
| NASA GSFC GK2A hourly fire detections, Zenodo 10.5281/zenodo.20084790 | Backtest config B and the afternoon ratio (phase 2, not ingested here) | CC BY 4.0 | "GK2A hourly fire detections for Punjab and Haryana, NASA GSFC, doi:10.5281/zenodo.20084790, CC BY 4.0." |

## Notes on what each static file is

- `districts.geojson`: every geoBoundaries IND/PAK ADM2 unit whose bbox meets the domain, kept whole (not cut at the edge), coordinates rounded to 3 dp. Properties: `district`, `state` (ASCII, e.g. "Haryana"; Pakistani units are "Punjab (Pakistan)"), `country`, `gb_id`. Rebuild: `uv run python -m dhuaan.geo.districts`.
- `receptors.json`: `{attribution, receptors: [{id, name, kind, district, state, lat, lon, population}]}`. IDs: `gn-<geonameid>`, `osm-<n|w|r><osm id>`, `dlw-<ward no>`. Rebuild: `uv run python -m dhuaan.geo.receptors` (also writes `demo_places.json`).
- `demo_places.json`: the demo school (a real OSM school in Bhawanigarh, Sangrur; the principal persona is fictional), the Rohini ward and Patiala.
- `population_0p1.json`: `{lon0, lat0, dlon, dlat, nx: 66, ny: 48, row0: "south", total, rows}` persons per cell. Rebuild: `uv run python -m dhuaan.geo.population` (about 4 minutes of HTTP range reads; the reader is pure Python, no GDAL).
- `aq_stations.json`: OpenAQ locations in the domain with a PM2.5 sensor (`is_monitor` = reference-grade). Rebuild: `uv run python -m dhuaan.ingest.openaq`.
