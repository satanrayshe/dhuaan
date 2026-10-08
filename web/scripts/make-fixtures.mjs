#!/usr/bin/env node
/**
 * Synthetic, schema-valid fixtures for the Dhuaan web app.
 *
 * Writes CONTRACTS.md artifacts 1-9 into web/public/data/latest/ so the UI can be
 * built and demoed before the real pipeline output lands. Every file is marked as
 * sample data through meta.json -> "synthetic": true, and the UI shows a badge.
 *
 * The numbers come from a tiny Lagrangian toy model (NW winds, diurnal boundary
 * layer, random-walk diffusion) so fires, trails, the smoke field, place series,
 * attribution and exposure are mutually consistent. It is NOT the real model.
 *
 * Usage: node scripts/make-fixtures.mjs [--t0 2026-10-08T10:00:00Z] [--seed 7] [--out public/data/latest]
 */
import { mkdirSync, writeFileSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, a, i, all) => {
    if (a.startsWith("--")) acc.push([a.slice(2), all[i + 1]]);
    return acc;
  }, []),
);
const OUT = resolve(here, "..", args.out ?? "public/data/latest");
const SEED = Number(args.seed ?? 7);

// ---------------------------------------------------------------- constants
const DOMAIN = { lon0: 72.5, lon1: 79.0, lat0: 28.0, lat1: 32.75 };
const NX = 66, NY = 48, D = 0.1;
const HOURS = 97; // -24 .. +72
const IST = 5.5 * 3600e3;
const H = 3600e3;

const t0 = (() => {
  const base = args.t0 ? new Date(args.t0) : new Date();
  const ms = Math.floor(base.getTime() / H) * H;
  return new Date(ms);
})();
const tStart = new Date(t0.getTime() - 24 * H);
const iso = (d) => new Date(d).toISOString().replace(/\.\d{3}Z$/, "Z");
const istHour = (ms) => (((ms + IST) / H) % 24 + 24) % 24;

// ---------------------------------------------------------------- rng
function mulberry32(a) {
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = mulberry32(SEED);
const gauss = () => {
  let u = 0, v = 0;
  while (u === 0) u = rand();
  while (v === 0) v = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
};
const pick = (arr) => arr[Math.floor(rand() * arr.length)];
const r2 = (x) => Math.round(x * 100) / 100;
const r4 = (x) => Math.round(x * 1e4) / 1e4;

// ---------------------------------------------------------------- geography
// district centroids (approximate) for the lookup
const DISTRICTS = [
  ["Amritsar", "Punjab", 74.87, 31.63], ["Tarn Taran", "Punjab", 74.93, 31.45],
  ["Gurdaspur", "Punjab", 75.4, 32.04], ["Kapurthala", "Punjab", 75.38, 31.38],
  ["Jalandhar", "Punjab", 75.58, 31.33], ["Hoshiarpur", "Punjab", 75.91, 31.53],
  ["Ludhiana", "Punjab", 75.85, 30.9], ["Moga", "Punjab", 75.17, 30.8],
  ["Ferozepur", "Punjab", 74.6, 30.92], ["Fazilka", "Punjab", 74.03, 30.4],
  ["Sri Muktsar Sahib", "Punjab", 74.52, 30.47], ["Faridkot", "Punjab", 74.75, 30.67],
  ["Bathinda", "Punjab", 74.95, 30.21], ["Mansa", "Punjab", 75.39, 29.99],
  ["Barnala", "Punjab", 75.55, 30.38], ["Sangrur", "Punjab", 75.84, 30.25],
  ["Malerkotla", "Punjab", 75.88, 30.53], ["Patiala", "Punjab", 76.39, 30.34],
  ["Fatehgarh Sahib", "Punjab", 76.39, 30.65], ["Rupnagar", "Punjab", 76.53, 30.97],
  ["Chandigarh", "Chandigarh", 76.78, 30.73], ["Ambala", "Haryana", 76.78, 30.38],
  ["Kurukshetra", "Haryana", 76.85, 29.97], ["Kaithal", "Haryana", 76.4, 29.8],
  ["Karnal", "Haryana", 76.98, 29.69], ["Panipat", "Haryana", 76.97, 29.39],
  ["Jind", "Haryana", 76.32, 29.32], ["Fatehabad", "Haryana", 75.45, 29.52],
  ["Sirsa", "Haryana", 75.03, 29.53], ["Hisar", "Haryana", 75.72, 29.15],
  ["Rohtak", "Haryana", 76.61, 28.9], ["Sonipat", "Haryana", 77.02, 28.99],
  ["Jhajjar", "Haryana", 76.66, 28.61], ["Gurugram", "Haryana", 77.03, 28.46],
  ["North West Delhi", "Delhi", 77.07, 28.72], ["Central Delhi", "Delhi", 77.22, 28.65],
  ["East Delhi", "Delhi", 77.3, 28.63], ["South West Delhi", "Delhi", 77.03, 28.58],
  ["Gautam Buddh Nagar", "Uttar Pradesh", 77.45, 28.5], ["Ghaziabad", "Uttar Pradesh", 77.43, 28.67],
  ["Meerut", "Uttar Pradesh", 77.7, 28.98], ["Sri Ganganagar", "Rajasthan", 73.88, 29.9],
  ["Hanumangarh", "Rajasthan", 74.33, 29.58],
];
function districtOf(lon, lat) {
  let best = DISTRICTS[0], bd = Infinity;
  for (const d of DISTRICTS) {
    const dd = (d[2] - lon) ** 2 * Math.cos((lat * Math.PI) / 180) ** 2 + (d[3] - lat) ** 2;
    if (dd < bd) { bd = dd; best = d; }
  }
  return { district: best[0], state: best[1] };
}

// receptors: [id, name, kind, lon, lat, population]
const RECEPTORS = [
  // demo school (fictional persona, real town)
  ["school-bhawanigarh-gsss", "Govt. Senior Secondary School, Bhawanigarh", "school", 76.04, 30.266, 1150],
  ["school-sangrur-gghs", "Govt. Girls High School, Sangrur", "school", 75.845, 30.247, 820],
  ["school-sunam-gsss", "Govt. Senior Secondary School, Sunam", "school", 75.877, 30.128, 960],
  ["school-patiala-model", "Govt. Model School, Patiala", "school", 76.395, 30.335, 1400],
  ["school-rohini-sv", "Sarvodaya Vidyalaya, Rohini Sector 8", "school", 77.105, 28.708, 1800],
  ["school-bathinda-gsss", "Govt. Senior Secondary School, Bathinda", "school", 74.952, 30.205, 1300],
  ["school-dhuri-gsss", "Govt. Senior Secondary School, Dhuri", "school", 75.875, 30.37, 900],
  // Delhi wards (pre-2022 names)
  ["ward-rohini", "Rohini", "ward", 77.067, 28.736, 310000],
  ["ward-punjabi-bagh", "Punjabi Bagh", "ward", 77.131, 28.668, 180000],
  ["ward-anand-vihar", "Anand Vihar", "ward", 77.315, 28.647, 150000],
  ["ward-dwarka", "Dwarka", "ward", 77.046, 28.592, 290000],
  ["ward-narela", "Narela", "ward", 77.093, 28.853, 240000],
  ["ward-karol-bagh", "Karol Bagh", "ward", 77.19, 28.652, 160000],
  // towns and cities
  ["town-bhawanigarh", "Bhawanigarh", "town", 76.04, 30.266, 24000],
  ["city-sangrur", "Sangrur", "city", 75.844, 30.245, 90000],
  ["town-sunam", "Sunam", "town", 75.878, 30.128, 60000],
  ["town-dhuri", "Dhuri", "town", 75.869, 30.368, 55000],
  ["town-lehragaga", "Lehragaga", "town", 75.97, 29.94, 22000],
  ["city-patiala", "Patiala", "city", 76.386, 30.34, 450000],
  ["town-samana", "Samana", "town", 76.19, 30.155, 55000],
  ["town-nabha", "Nabha", "town", 76.15, 30.374, 70000],
  ["city-bathinda", "Bathinda", "city", 74.951, 30.211, 300000],
  ["city-mansa", "Mansa", "city", 75.393, 29.988, 90000],
  ["city-barnala", "Barnala", "city", 75.546, 30.378, 120000],
  ["city-ludhiana", "Ludhiana", "city", 75.857, 30.901, 1700000],
  ["city-moga", "Moga", "city", 75.172, 30.816, 160000],
  ["city-amritsar", "Amritsar", "city", 74.872, 31.634, 1200000],
  ["city-jalandhar", "Jalandhar", "city", 75.576, 31.326, 870000],
  ["city-ferozepur", "Ferozepur", "city", 74.613, 30.925, 110000],
  ["city-chandigarh", "Chandigarh", "city", 76.779, 30.733, 1100000],
  ["city-ambala", "Ambala", "city", 76.777, 30.378, 210000],
  ["city-kaithal", "Kaithal", "city", 76.399, 29.801, 150000],
  ["city-karnal", "Karnal", "city", 76.99, 29.686, 300000],
  ["city-panipat", "Panipat", "city", 76.968, 29.391, 450000],
  ["city-sonipat", "Sonipat", "city", 77.016, 28.994, 280000],
  ["city-jind", "Jind", "city", 76.316, 29.316, 170000],
  ["city-hisar", "Hisar", "city", 75.722, 29.149, 300000],
  ["city-rohtak", "Rohtak", "city", 76.606, 28.895, 375000],
  ["city-sirsa", "Sirsa", "city", 75.025, 29.534, 180000],
  ["city-gurugram", "Gurugram", "city", 77.026, 28.459, 1500000],
  ["city-noida", "Noida", "city", 77.391, 28.535, 640000],
  ["city-ghaziabad", "Ghaziabad", "city", 77.438, 28.669, 1700000],
  ["city-meerut", "Meerut", "city", 77.706, 28.984, 1300000],
  ["city-new-delhi", "New Delhi", "city", 77.209, 28.614, 250000],
  // villages around the Sangrur / Patiala belt
  ["village-ghabdan", "Ghabdan", "village", 75.93, 30.29, 4200],
  ["village-kakra", "Kakra", "village", 76.0, 30.31, 3100],
  ["village-balad-kalan", "Balad Kalan", "village", 76.07, 30.22, 3800],
  ["village-kanoi", "Kanoi", "village", 76.11, 30.3, 2600],
  ["village-ladal", "Ladal", "village", 75.98, 30.18, 2900],
  ["village-ghanaur", "Ghanaur", "village", 76.57, 30.33, 9000],
  ["village-sanaur", "Sanaur", "village", 76.48, 30.3, 14000],
  ["village-bhadaur", "Bhadaur", "village", 75.33, 30.47, 16000],
  ["village-maur", "Maur", "village", 75.22, 30.08, 21000],
  ["village-rampura-phul", "Rampura Phul", "village", 75.23, 30.27, 30000],
];

// fire belts: [district centroid lon, lat, number of clusters]
const BELTS = [
  [75.84, 30.25, 26], [76.3, 30.3, 15], [74.95, 30.2, 14], [75.39, 29.99, 10],
  [75.55, 30.38, 8], [74.62, 30.9, 9], [75.17, 30.79, 8], [74.93, 31.43, 8],
  [75.75, 30.82, 6], [74.87, 31.6, 5], [74.52, 30.48, 6], [76.4, 29.8, 6],
  [75.48, 29.52, 5], [76.32, 29.35, 4], [76.95, 29.68, 3], [76.85, 29.97, 3],
];

// ---------------------------------------------------------------- met
const BLH = (ms) => {
  const h = istHour(ms);
  const day = h > 7 && h < 18 ? Math.sin((Math.PI * (h - 7)) / 11) : 0;
  return 150 + 1100 * Math.max(0, day); // metres
};
function wind(lon, lat, ms) {
  const h = istHour(ms);
  const day = h > 9 && h < 17;
  const speed = (day ? 3.4 : 0.9) * (1 + 0.15 * Math.sin(lon * 2.1 + lat));
  const hoursFromT0 = (ms - t0.getTime()) / H;
  // bearing the air moves toward: SSE now, veering to ESE on day 2
  let bearing = 146 + (lat - 30) * 6;
  if (hoursFromT0 > 30) bearing -= Math.min(26, (hoursFromT0 - 30) * 1.2);
  const b = (bearing * Math.PI) / 180;
  return [speed * Math.sin(b), speed * Math.cos(b)];
}

// ---------------------------------------------------------------- fires
const fires = [];
const clusters = [];
let fireSeq = 0;
const tMs0 = tStart.getTime(), tMs1 = t0.getTime();
const istMidnightBefore = (ms) => Math.floor((ms + IST) / (24 * H)) * 24 * H - IST;
const days = [istMidnightBefore(tMs0), istMidnightBefore(tMs0) + 24 * H];

let clusterSeq = 0;
for (const [blon, blat, n] of BELTS) {
  for (let k = 0; k < n; k++) {
    const lon = blon + gauss() * 0.16;
    const lat = blat + gauss() * 0.12;
    const intensity = Math.exp(gauss() * 0.7) * (blon > 75.6 && blon < 76.2 ? 1.5 : 1);
    // pattern: 0 = midday only, 1 = midday + evening, 2 = evening only (missed by midday pass)
    const r = rand();
    const pattern = r < 0.38 ? 0 : r < 0.68 ? 1 : 2;
    const cid = `c${String(++clusterSeq).padStart(3, "0")}`;
    const dets = [];
    for (const day of days) {
      if (pattern !== 2) {
        const nMid = 1 + Math.floor(rand() * 4 * Math.min(2, intensity));
        for (let i = 0; i < nMid; i++) {
          const sensor = pick(["VIIRS_SNPP", "VIIRS_NOAA20", "VIIRS_NOAA21", "VIIRS_NOAA20", "MODIS"]);
          const hh = sensor === "MODIS" ? 10.6 + rand() * 0.4 : 13.1 + rand() * 0.9;
          dets.push({ sensor, ms: day + hh * H, frp: Math.max(1.2, Math.exp(1.9 + gauss() * 0.8) * intensity) });
        }
      }
      if (pattern !== 0) {
        const nEve = 1 + Math.floor(rand() * 3 * Math.min(2, intensity));
        for (let i = 0; i < nEve; i++) {
          const hh = 15.6 + rand() * 3.4;
          dets.push({ sensor: "MSG_IODC", ms: day + hh * H, frp: Math.max(8, Math.exp(3.2 + gauss() * 0.6) * intensity) });
        }
      }
    }
    const inWin = dets.filter((d) => d.ms >= tMs0 && d.ms <= tMs1);
    if (!inWin.length) continue;
    const feats = inWin.map((d) => {
      const f = {
        id: `f${String(++fireSeq).padStart(5, "0")}`,
        lon: r4(lon + gauss() * 0.006),
        lat: r4(lat + gauss() * 0.005),
        ms: Math.round(d.ms / 60e3) * 60e3,
        sensor: d.sensor,
        frp_mw: r2(d.frp),
        confidence: d.sensor === "MSG_IODC" ? pick(["low", "nominal", "nominal"]) : pick(["nominal", "high", "nominal"]),
        cluster_id: cid,
      };
      f.afternoon = istHour(f.ms) >= 15;
      return f;
    });
    fires.push(...feats);
    clusters.push({ cluster_id: cid, lat, lon, fires: feats, ...districtOf(lon, lat) });
  }
}

// ---------------------------------------------------------------- particles
// emissions: each detection burns for ~2 h. Forecast assumption for the toy model:
// the same clusters burn again on the following two days at 60 % of today's FRP.
const particles = [];
for (const c of clusters) {
  for (const f of c.fires) {
    for (let rep = 0; rep < 3; rep++) {
      const startMs = f.ms + rep * 24 * H;
      if (startMs > t0.getTime() + 70 * H) continue;
      const weight = f.frp_mw * (rep === 0 ? 1 : 0.6);
      const n = Math.max(2, Math.min(9, Math.round(Math.sqrt(weight) * 0.9)));
      for (let i = 0; i < n; i++) {
        particles.push({
          cluster: c.cluster_id,
          lon: f.lon, lat: f.lat,
          release: startMs + rand() * 2 * H,
          w: weight / n,
          trip: rep < 2,
        });
      }
    }
  }
}

const DT = 15 * 60e3;
const endMs = t0.getTime() + 72 * H;
const TAU = 48 * H;
// positions at whole hours (index -> [lon, lat, w]) for every particle
const hourIdx = (ms) => Math.round((ms - tMs0) / H);
for (const p of particles) {
  p.hours = new Map();
  p.path = [];
  p.ts = [];
  let ms = p.release, lon = p.lon, lat = p.lat;
  const kmx = () => 111.32 * Math.cos((lat * Math.PI) / 180);
  let lastRec = -Infinity;
  while (ms < endMs) {
    // RK2 midpoint
    const [u1, v1] = wind(lon, lat, ms);
    const dtS = DT / 1000;
    const mLon = lon + (u1 * dtS / 2 / 1000) / kmx();
    const mLat = lat + (v1 * dtS / 2 / 1000) / 110.54;
    const [u2, v2] = wind(mLon, mLat, ms + DT / 2);
    const K = BLH(ms) > 400 ? 5000 : 1000;
    const sigma = Math.sqrt(2 * K * (DT / 1000)) / 1000; // km
    lon += ((u2 * dtS) / 1000 + gauss() * sigma) / kmx();
    lat += ((v2 * dtS) / 1000 + gauss() * sigma) / 110.54;
    ms += DT;
    if (lon < DOMAIN.lon0 || lon > DOMAIN.lon1 || lat < DOMAIN.lat0 || lat > DOMAIN.lat1) break;
    const w = p.w * Math.exp(-(ms - p.release) / TAU);
    if (Math.floor((ms - DT) / H) !== Math.floor(ms / H)) p.hours.set(hourIdx(Math.floor(ms / H) * H), [lon, lat, w]);
    if (p.trip && ms - lastRec >= 60 * 60e3 && ms - p.release <= 30 * H) {
      if (p.path.length === 0) { p.path.push([r4(p.lon), r4(p.lat)]); p.ts.push(Math.round((p.release - tMs0) / 60e3)); }
      p.path.push([r4(lon), r4(lat)]);
      p.ts.push(Math.round((ms - tMs0) / 60e3));
      lastRec = ms;
    }
  }
}

// ---------------------------------------------------------------- population grid
const pop = new Float64Array(NX * NY);
const CITYPOP = RECEPTORS.filter((r) => r[2] === "city" || r[2] === "ward").map((r) => [r[3], r[4], r[5], r[2] === "ward" ? 0.04 : 0.06]);
CITYPOP.push([77.15, 28.65, 9e6, 0.14]);
for (let j = 0; j < NY; j++) for (let i = 0; i < NX; i++) {
  const lon = DOMAIN.lon0 + (i + 0.5) * D, lat = DOMAIN.lat0 + (j + 0.5) * D;
  const rural = lon < 73.8 || lat < 28.6 && lon < 75.5 ? 150 : 480;
  let p = rural * 110;
  for (const [cx, cy, cp, s] of CITYPOP) {
    const d2 = (cx - lon) ** 2 + (cy - lat) ** 2;
    if (d2 < 0.4) p += (cp * Math.exp(-d2 / (2 * s * s)) * D * D) / (2 * Math.PI * s * s);
  }
  pop[j * NX + i] = p;
}

// ---------------------------------------------------------------- concentration
const KH = 10; // km kernel width
const kernel = (dxKm, dyKm) => Math.exp(-(dxKm * dxKm + dyKm * dyKm) / (2 * KH * KH)) / (2 * Math.PI * KH * KH);
const grid = Array.from({ length: HOURS }, () => new Float64Array(NX * NY));
const nR = RECEPTORS.length;
const cIndex = new Map(clusters.map((c, i) => [c.cluster_id, i]));
const nC = clusters.length;
// receptor x cluster x hour contributions
const contrib = Array.from({ length: nR }, () => Array.from({ length: nC }, () => new Float64Array(HOURS)));
const exposure = new Float64Array(nC);
const exposureCell = (h) => h >= 24 && h <= 24 + 48;

for (const p of particles) {
  const ci = cIndex.get(p.cluster);
  for (const [h, [lon, lat, w]] of p.hours) {
    if (h < 0 || h >= HOURS) continue;
    const blh = BLH(tMs0 + h * H) / 1000;
    const amp = (w / blh) * 1000;
    const g = grid[h];
    const ic = Math.floor((lon - DOMAIN.lon0) / D), jc = Math.floor((lat - DOMAIN.lat0) / D);
    for (let dj = -3; dj <= 3; dj++) for (let di = -3; di <= 3; di++) {
      const i = ic + di, j = jc + dj;
      if (i < 0 || j < 0 || i >= NX || j >= NY) continue;
      const clon = DOMAIN.lon0 + (i + 0.5) * D, clat = DOMAIN.lat0 + (j + 0.5) * D;
      const v = amp * kernel((clon - lon) * 111.32 * Math.cos((lat * Math.PI) / 180), (clat - lat) * 110.54);
      g[j * NX + i] += v;
      if (exposureCell(h)) exposure[ci] += v * pop[j * NX + i];
    }
    for (let r = 0; r < nR; r++) {
      const [, , , rlon, rlat] = RECEPTORS[r];
      const dx = (rlon - lon) * 111.32 * Math.cos((lat * Math.PI) / 180), dy = (rlat - lat) * 110.54;
      if (Math.abs(dx) > 40 || Math.abs(dy) > 40) continue;
      contrib[r][ci][h] += amp * kernel(dx, dy);
    }
  }
}

// scale: 99th percentile of positive smoke over the run
const positives = [];
for (const g of grid) for (const v of g) if (v > 1e-6) positives.push(v);
positives.sort((a, b) => a - b);
const rawScale = positives[Math.floor(positives.length * 0.99)] || 1;
// express smoke units so that scale is a round-ish number (~4 smoke units)
const UNIT = 4 / rawScale;
const scale = r2(rawScale * UNIT);
const threshold = r2(0.15 * scale);

// ---------------------------------------------------------------- places
// AQ stations (names of real CPCB sites; readings here are synthetic)
const AQ_STATIONS = [
  { name: "Patiala - Model Town", lon: 76.37, lat: 30.33, base: 48 },
  { name: "Bathinda - Hardev Nagar", lon: 74.93, lat: 30.22, base: 55 },
  { name: "Ludhiana - Punjab Agricultural University", lon: 75.8, lat: 30.9, base: 62 },
  { name: "Amritsar - Golden Temple", lon: 74.88, lat: 31.62, base: 58 },
  { name: "Rohini - DPCC", lon: 77.1, lat: 28.73, base: 92 },
  { name: "Punjabi Bagh - DPCC", lon: 77.13, lat: 28.67, base: 96 },
  { name: "Anand Vihar - DPCC", lon: 77.32, lat: 28.65, base: 118 },
  { name: "Dwarka Sector 8 - DPCC", lon: 77.07, lat: 28.57, base: 88 },
];
const timeAt = (h) => iso(tMs0 + h * H);
const places = [];
const receptorSeries = RECEPTORS.map((_, r) => {
  const s = new Float64Array(HOURS);
  for (let ci = 0; ci < nC; ci++) for (let h = 0; h < HOURS; h++) s[h] += contrib[r][ci][h] * UNIT;
  // light temporal smoothing (the toy model is noisy at receptors)
  const out = new Float64Array(HOURS);
  for (let h = 0; h < HOURS; h++) {
    let acc = 0, ws = 0;
    for (let k = -2; k <= 2; k++) { const hh = h + k; if (hh < 0 || hh >= HOURS) continue; const w = 3 - Math.abs(k); acc += s[hh] * w; ws += w; }
    out[h] = acc / ws;
  }
  return out;
});

const firstCross = (series, thr) => { for (let h = 24; h < HOURS; h++) if (series[h] >= thr) return h; return null; };

// alpha: "calibrated" for the sample so the UI can exercise the PM2.5 path
let maxDelhi = 0;
RECEPTORS.forEach((rc, r) => { if (rc[0] === "ward-rohini") maxDelhi = Math.max(...receptorSeries[r].slice(24)); });
const ALPHA = r2(maxDelhi > 0 ? 210 / maxDelhi : 40);

RECEPTORS.forEach((rc, r) => {
  const [id, name, kind, lon, lat, population] = rc;
  const series = Array.from(receptorSeries[r], r2);
  const p10 = series.map((v, h) => r2(Math.max(0, Math.min(...series.slice(Math.max(0, h - 2), h + 3)) * 0.62)));
  const p90 = series.map((v, h) => r2(Math.max(...series.slice(Math.max(0, h - 3), h + 4)) * 1.45 + 0.02));
  let peakH = 24;
  for (let h = 24; h < HOURS; h++) if (series[h] > series[peakH]) peakH = h;
  const arr = firstCross(series, threshold);
  const early = firstCross(p90, threshold);
  const late = firstCross(p10, threshold);
  // attribution over t0 .. t0+48h by district
  const byDistrict = new Map();
  const byCluster = [];
  let total = 0;
  clusters.forEach((c, ci) => {
    let s = 0;
    for (let h = 24; h <= 72; h++) s += contrib[r][ci][h];
    if (s <= 0) return;
    total += s;
    byCluster.push({ cluster_id: c.cluster_id, s });
    const key = `${c.district}|${c.state}`;
    byDistrict.set(key, (byDistrict.get(key) ?? 0) + s);
  });
  const sortedD = [...byDistrict.entries()].sort((a, b) => b[1] - a[1]);
  const attribution = sortedD.slice(0, 5).map(([k, s]) => {
    const [district, state] = k.split("|");
    return { district, state, share: r2(s / total) };
  });
  const rest = sortedD.slice(5).reduce((a, [, s]) => a + s, 0);
  if (rest > 0) attribution.push({ district: "Other", state: "", share: r2(rest / total) });
  const top_clusters = byCluster.sort((a, b) => b.s - a.s).slice(0, 5).map((c) => ({ cluster_id: c.cluster_id, share: r2(c.s / total) }));
  const { district, state } = districtOf(lon, lat);
  const nearestStation = AQ_STATIONS.reduce((best, s) => {
    const d = (s.lon - lon) ** 2 + (s.lat - lat) ** 2;
    return d < best.d ? { s, d } : best;
  }, { s: null, d: Infinity });
  const place = {
    id, name, kind, district, state, lat, lon,
    t0_utc: iso(t0),
    series, p10, p90,
    arrival_utc: arr === null ? null : timeAt(arr),
    arrival_window: early === null ? null : [timeAt(early), timeAt(late ?? Math.min(HOURS - 1, (arr ?? early) + 4))],
    peak_utc: timeAt(peakH),
    peak_smoke: series[peakH],
    attribution: total > 0 ? attribution : [],
    top_clusters,
  };
  // optional extension (not yet in CONTRACTS): latest monitor reading near the place
  if (nearestStation.s && nearestStation.d < 0.25) {
    const s = nearestStation.s;
    const pm = Math.round(s.base + series[24] * ALPHA * 0.8);
    place.aq_now = { station: s.name, provider: "CPCB via OpenAQ", pm25: pm, category: naqi(pm), obs_utc: iso(t0.getTime() - 40 * 60e3) };
  }
  places.push({ place, population, series });
});

function naqi(pm) {
  if (pm <= 30) return "good";
  if (pm <= 60) return "satisfactory";
  if (pm <= 90) return "moderate";
  if (pm <= 120) return "poor";
  if (pm <= 250) return "very_poor";
  return "severe";
}


// ---------------------------------------------------------------- clusters.json
const totalExposure = exposure.reduce((a, b) => a + b, 0) || 1;
const clusterOut = clusters.map((c, ci) => {
  const fs = c.fires;
  const nearest = RECEPTORS.filter((r) => r[2] !== "school" && r[2] !== "ward").reduce((best, r) => {
    const d = (r[3] - c.lon) ** 2 + (r[4] - c.lat) ** 2;
    return d < best.d ? { r, d } : best;
  }, { r: null, d: Infinity }).r;
  const downwind = RECEPTORS.map((rc, r) => {
    let s = 0, pk = 24;
    for (let h = 24; h <= 72; h++) { s += contrib[r][ci][h] * rc[5]; if (contrib[r][ci][h] > contrib[r][ci][pk]) pk = h; }
    const ser = contrib[r][ci];
    let arr = null;
    for (let h = 24; h < HOURS; h++) if (ser[h] * UNIT >= threshold * 0.25) { arr = h; break; }
    return { s, place_id: rc[0], name: rc[1], kind: rc[2], arrival_utc: arr === null ? null : timeAt(arr), peak_utc: timeAt(pk), peak_smoke: r2(ser[pk] * UNIT) };
  }).filter((d) => d.s > 0).sort((a, b) => b.s - a.s).slice(0, 5).map((d) => { const out = { ...d }; delete out.s; return out; });
  return {
    cluster_id: c.cluster_id,
    lat: r4(c.lat), lon: r4(c.lon),
    n_detections: fs.length,
    frp_sum_mw: r2(fs.reduce((a, f) => a + f.frp_mw, 0)),
    first_seen_utc: iso(Math.min(...fs.map((f) => f.ms))),
    last_seen_utc: iso(Math.max(...fs.map((f) => f.ms))),
    district: c.district, state: c.state,
    nearest_place: nearest ? nearest[1] : c.district,
    exposure_person_hours: Math.round((exposure[ci] * UNIT) / scale),
    exposure_share: Math.round((exposure[ci] / totalExposure) * 1e4) / 1e4,
    downwind,
  };
}).sort((a, b) => b.exposure_share - a.exposure_share).map((c, i) => ({ ...c, rank: i + 1 }));

// ---------------------------------------------------------------- grid.json
const frames = grid.map((g) => {
  const bytes = new Uint8Array(NX * NY);
  for (let k = 0; k < g.length; k++) bytes[k] = Math.round(255 * Math.min(1, (g[k] * UNIT) / scale));
  return Buffer.from(bytes).toString("base64");
});

// ---------------------------------------------------------------- trips.json
let trips = particles.filter((p) => p.path.length > 2).map((p) => ({ cluster_id: p.cluster, path: p.path, ts: p.ts }));
if (trips.length > 6000) {
  const step = trips.length / 6000;
  trips = Array.from({ length: 6000 }, (_, i) => trips[Math.floor(i * step)]);
}

// ---------------------------------------------------------------- advisories
const schoolDay = (() => {
  // the next school day whose 07-14 IST window is inside t0 .. t0+72h
  const nowIst = t0.getTime() + IST;
  const dayStart = Math.floor(nowIst / (24 * H)) * 24 * H; // IST midnight in "IST ms"
  const today14 = dayStart + 14 * H;
  const base = nowIst < today14 - 6 * H ? dayStart : dayStart + 24 * H;
  return base; // IST-ms midnight
})();
const dateIst = new Date(schoolDay).toISOString().slice(0, 10);
const CAT_LABEL = {
  en: { good: "Good", satisfactory: "Satisfactory", moderate: "Moderate", poor: "Poor", very_poor: "Very poor", severe: "Severe" },
  hi: { good: "अच्छा", satisfactory: "संतोषजनक", moderate: "मध्यम", poor: "खराब", very_poor: "बहुत खराब", severe: "गंभीर" },
  pa: { good: "ਚੰਗਾ", satisfactory: "ਤਸੱਲੀਬਖ਼ਸ਼", moderate: "ਦਰਮਿਆਨਾ", poor: "ਮਾੜਾ", very_poor: "ਬਹੁਤ ਮਾੜਾ", severe: "ਗੰਭੀਰ" },
};
const advisories = places.filter(({ place }) => place.kind === "school").map(({ place, series }) => {
  const plan = [];
  for (let hIst = 7; hIst <= 14; hIst++) {
    const utcMs = schoolDay - IST + hIst * H;
    const idx = Math.round((utcMs - tMs0) / H);
    const pm = Math.round(Math.max(0, series[Math.max(0, Math.min(HOURS - 1, idx))]) * ALPHA + 22);
    const category = naqi(pm);
    const outdoor = pm <= 60 ? "ok" : pm <= 120 ? "limit" : "indoors";
    plan.push({ hour_ist: hIst, est_pm25: pm, category, outdoor });
  }
  const worst = plan.reduce((a, b) => (b.est_pm25 > a.est_pm25 ? b : a));
  const ok = plan.filter((p) => p.outdoor === "ok").map((p) => p.hour_ist);
  const okText = ok.length ? `${String(ok[0]).padStart(2, "0")}:00-${String(ok[ok.length - 1] + 1).padStart(2, "0")}:00` : null;
  const name = place.name;
  const cat = (l) => CAT_LABEL[l][worst.category];
  const notice = {
    en: `Dear parents, ${name}: smoke from crop-residue fires is forecast over our area on ${dateIst}. Estimated PM2.5 peaks at ${worst.est_pm25} µg/m³ (${cat("en")}) around ${String(worst.hour_ist).padStart(2, "0")}:00. ${worst.outdoor === "indoors" ? "Morning assembly and sports will be held indoors." : worst.outdoor === "limit" ? "Outdoor activity will be short and light." : "Normal outdoor activity is planned."}${okText ? ` Outdoor time is planned for ${okText}.` : ""} Children with asthma should carry their inhaler. This is a forecast, not a measurement.`,
    hi: `प्रिय अभिभावक, ${name}: ${dateIst} को हमारे क्षेत्र में पराली के धुएँ का पूर्वानुमान है। अनुमानित PM2.5 लगभग ${String(worst.hour_ist).padStart(2, "0")}:00 बजे ${worst.est_pm25} µg/m³ (${cat("hi")}) तक पहुँच सकता है। ${worst.outdoor === "indoors" ? "सुबह की प्रार्थना सभा और खेल कक्षा के अंदर होंगे।" : worst.outdoor === "limit" ? "बाहर की गतिविधियाँ कम और हल्की रहेंगी।" : "बाहर की सामान्य गतिविधियाँ होंगी।"}${okText ? ` बाहर का समय ${okText} रखा गया है।` : ""} दमा वाले बच्चे अपना इनहेलर साथ रखें। यह पूर्वानुमान है, माप नहीं।`,
    pa: `ਪਿਆਰੇ ਮਾਪਿਓ, ${name}: ${dateIst} ਨੂੰ ਸਾਡੇ ਇਲਾਕੇ ਵਿੱਚ ਪਰਾਲੀ ਦੇ ਧੂੰਏਂ ਦੀ ਭਵਿੱਖਬਾਣੀ ਹੈ। ਅਨੁਮਾਨਿਤ PM2.5 ਲਗਭਗ ${String(worst.hour_ist).padStart(2, "0")}:00 ਵਜੇ ${worst.est_pm25} µg/m³ (${cat("pa")}) ਤੱਕ ਪਹੁੰਚ ਸਕਦਾ ਹੈ। ${worst.outdoor === "indoors" ? "ਸਵੇਰ ਦੀ ਸਭਾ ਅਤੇ ਖੇਡਾਂ ਅੰਦਰ ਹੋਣਗੀਆਂ।" : worst.outdoor === "limit" ? "ਬਾਹਰ ਦੀਆਂ ਗਤੀਵਿਧੀਆਂ ਥੋੜ੍ਹੀਆਂ ਅਤੇ ਹਲਕੀਆਂ ਰਹਿਣਗੀਆਂ।" : "ਬਾਹਰ ਦੀਆਂ ਆਮ ਗਤੀਵਿਧੀਆਂ ਹੋਣਗੀਆਂ।"}${okText ? ` ਬਾਹਰ ਦਾ ਸਮਾਂ ${okText} ਰੱਖਿਆ ਗਿਆ ਹੈ।` : ""} ਦਮੇ ਵਾਲੇ ਬੱਚੇ ਆਪਣਾ ਇਨਹੇਲਰ ਨਾਲ ਰੱਖਣ। ਇਹ ਭਵਿੱਖਬਾਣੀ ਹੈ, ਮਾਪ ਨਹੀਂ।`,
  };
  const nums = 2 + (okText ? 2 : 0);
  return { school_id: place.id, date_ist: dateIst, plan, notice, grounding: { verified: nums, total: nums }, model: "template (sample data)" };
});

// ---------------------------------------------------------------- backtest.json (sample)
const btStations = [
  { id: "cpcb-patiala", name: "Patiala - Model Town", lat: 30.33, lon: 76.37, lag: 4, amp: 70 },
  { id: "cpcb-bathinda", name: "Bathinda - Hardev Nagar", lat: 30.22, lon: 74.93, lag: 2, amp: 55 },
  { id: "dpcc-rohini", name: "Rohini - DPCC", lat: 28.73, lon: 77.1, lag: 18, amp: 120 },
  { id: "dpcc-anand-vihar", name: "Anand Vihar - DPCC", lat: 28.65, lon: 77.32, lag: 22, amp: 105 },
];
const btStart = Date.UTC(2025, 10, 6, 0); // 6 Nov 2025 (held-out period)
const btHours = 15 * 24;
const episodeCentres = [2.6, 5.4, 8.9, 11.2, 13.7].map((d) => d * 24);
const bt = btStations.map((s, si) => {
  const series = [];
  for (let k = 0; k < btHours; k += 3) {
    const sig = episodeCentres.reduce((a, c, ei) => a + (ei === 3 ? 1.6 : 1) * Math.exp(-(((k - c - s.lag) / 14) ** 2)), 0);
    const night = Math.cos(((istHour(btStart + k * H) - 4) / 24) * 2 * Math.PI) * 0.5 + 0.5;
    const obs = Math.max(0, s.amp * sig * (0.7 + 0.5 * night) + gauss() * 9);
    const predA = Math.max(0, s.amp * 0.78 * episodeCentres.reduce((a, c, ei) => a + (ei === 3 ? 0.9 : 1) * Math.exp(-(((k - c - s.lag - 3) / 13) ** 2)), 0) * (0.7 + 0.5 * night) + gauss() * 5);
    const predB = Math.max(0, s.amp * 0.93 * sig * (0.7 + 0.5 * night) + gauss() * 6 + si);
    series.push({ t: iso(btStart + k * H), obs_excess: r2(obs), pred_A: r2(predA), pred_B: r2(predB) });
  }
  return { id: s.id, name: s.name, lat: s.lat, lon: s.lon, series };
});
const backtest = {
  window: { calibration: ["2025-10-25", "2025-11-05"], evaluation: ["2025-11-06", "2025-11-20"], focus: "2025-11-11" },
  met_source: "Open-Meteo historical forecast API (archived forecasts) - SAMPLE",
  stations: bt,
  metrics: {
    A: { hit_rate: 0.6, false_alarm_ratio: 0.31, median_lead_h: 14, pearson_r: 0.52, episodes: 15, hits: 9 },
    B: { hit_rate: 0.8, false_alarm_ratio: 0.24, median_lead_h: 19, pearson_r: 0.67, episodes: 15, hits: 12 },
  },
  calibration: { alpha_A: 31.4, alpha_B: 27.9 },
  notes: "SAMPLE DATA generated by web/scripts/make-fixtures.mjs to exercise the UI. It is not a backtest result.",
};

// ---------------------------------------------------------------- meta.json
const viirsLatest = Math.max(...fires.filter((f) => f.sensor.startsWith("VIIRS")).map((f) => f.ms), tMs0);
const msgLatest = Math.max(...fires.filter((f) => f.sensor === "MSG_IODC").map((f) => f.ms), tMs0);
const meta = {
  run_id: `sample-${iso(t0).replace(/[-:]/g, "").slice(0, 13)}`,
  t0_utc: iso(t0),
  generated_utc: iso(t0.getTime() + 11 * 60e3),
  model_version: "fixture-0.1 (toy plume, not the Dhuaan model)",
  members: 5,
  afternoon_mode: "observed",
  alpha: ALPHA,
  calibrated: true,
  arrival_threshold: threshold,
  scale,
  domain: { lon0: DOMAIN.lon0, lon1: DOMAIN.lon1, lat0: DOMAIN.lat0, lat1: DOMAIN.lat1 },
  synthetic: true,
  sources: [
    { name: "NASA FIRMS VIIRS", fetched_utc: iso(t0.getTime() + 2 * 60e3), latest_obs_utc: iso(viirsLatest), count: fires.filter((f) => f.sensor.startsWith("VIIRS")).length, ok: true, note: "sample" },
    { name: "NASA FIRMS MODIS", fetched_utc: iso(t0.getTime() + 2 * 60e3), latest_obs_utc: iso(Math.max(...fires.filter((f) => f.sensor === "MODIS").map((f) => f.ms), tMs0)), count: fires.filter((f) => f.sensor === "MODIS").length, ok: true, note: "sample" },
    { name: "LSA SAF MSG-IODC FRP", fetched_utc: iso(t0.getTime() + 3 * 60e3), latest_obs_utc: iso(msgLatest), count: fires.filter((f) => f.sensor === "MSG_IODC").length, ok: true, note: "sample; geostationary, lower confidence" },
    { name: "Open-Meteo GFS", fetched_utc: iso(t0.getTime() + 4 * 60e3), latest_obs_utc: iso(Math.floor((t0.getTime() - 4 * H) / (6 * H)) * 6 * H), count: 540, ok: true, note: "sample" },
    { name: "OpenAQ", fetched_utc: iso(t0.getTime() + 5 * 60e3), latest_obs_utc: iso(t0.getTime() - 40 * 60e3), count: AQ_STATIONS.length, ok: true, note: "sample" },
  ],
};

// ---------------------------------------------------------------- write
rmSync(OUT, { recursive: true, force: true });
const write = (rel, obj) => {
  const p = join(OUT, rel);
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, JSON.stringify(obj));
};
write("meta.json", meta);
write("fires.geojson", {
  type: "FeatureCollection",
  features: fires.map((f) => ({
    type: "Feature",
    geometry: { type: "Point", coordinates: [f.lon, f.lat] },
    properties: { id: f.id, sensor: f.sensor, frp_mw: f.frp_mw, confidence: f.confidence, acq_utc: iso(f.ms), cluster_id: f.cluster_id, afternoon: f.afternoon },
  })),
});
write("clusters.json", { t0_utc: iso(t0), clusters: clusterOut });
write("trips.json", { t0_utc: iso(t0), step_minutes: 60, trips });
write("grid.json", { lon0: DOMAIN.lon0, lat0: DOMAIN.lat0, dlon: D, dlat: D, nx: NX, ny: NY, t0_utc: iso(t0), hours: HOURS, scale, frames });
write("receptors_index.json", {
  t0_utc: iso(t0),
  places: places.map(({ place: p }) => ({ id: p.id, name: p.name, kind: p.kind, district: p.district, state: p.state, lat: p.lat, lon: p.lon, peak_smoke: p.peak_smoke, peak_utc: p.peak_utc, arrival_utc: p.arrival_utc })),
});
for (const { place } of places) write(`places/${place.id}.json`, place);
for (const a of advisories) write(`advisories/${a.school_id}.json`, a);
write("backtest.json", backtest);

console.log(
  `fixtures -> ${OUT}\n t0 ${iso(t0)} | fires ${fires.length} (${fires.filter((f) => f.afternoon).length} after 15:00 IST) | clusters ${clusterOut.length} | trips ${trips.length} | places ${places.length} | scale ${scale} | alpha ${ALPHA}`,
);
