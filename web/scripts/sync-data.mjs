#!/usr/bin/env node
/**
 * Mirror the real pipeline output (backend/out/latest/**) into web/public/data/latest/
 * so `next dev` / `next build` serve it at /data/latest/... (that dir is gitignored).
 *
 * The destination is replaced, not merged: leftover synthetic fixtures (meta.synthetic,
 * a fake backtest.json) must not survive next to real data.
 *
 * Usage: node scripts/sync-data.mjs [--src ../backend/out/latest] [--dest public/data/latest]
 */
import { cpSync, existsSync, readFileSync, readdirSync, rmSync, statSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const arg = (name, dflt) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 ? process.argv[i + 1] : dflt;
};
const SRC = resolve(here, "..", arg("src", "../backend/out/latest"));
const DEST = resolve(here, "..", arg("dest", "public/data/latest"));

if (!existsSync(join(SRC, "meta.json"))) {
  console.error(`no pipeline output at ${SRC} (run: cd backend && uv run python -m dhuaan.pipeline.run_local)`);
  process.exit(1);
}

rmSync(DEST, { recursive: true, force: true });
cpSync(SRC, DEST, { recursive: true });

const meta = JSON.parse(readFileSync(join(DEST, "meta.json"), "utf8"));
const kb = (n) => `${(n / 1024).toFixed(0)} KB`;
const count = (d) => (existsSync(d) ? readdirSync(d).length : 0);
console.log(`synced run ${meta.run_id} (t0 ${meta.t0_utc}${meta.synthetic ? ", SYNTHETIC" : ""}) -> ${DEST}`);
for (const f of ["meta.json", "fires.geojson", "clusters.json", "trips.json", "grid.json", "receptors_index.json", "backtest.json", "baselines.json"]) {
  const p = join(DEST, f);
  if (!existsSync(p)) {
    console.log(`  ${f.padEnd(22)} (absent)`);
    continue;
  }
  const raw = readFileSync(p);
  console.log(`  ${f.padEnd(22)} ${kb(statSync(p).size).padStart(8)} raw  ${kb(gzipSync(raw).length).padStart(7)} gzip`);
}
console.log(`  places/                ${count(join(DEST, "places"))} files`);
console.log(`  advisories/            ${count(join(DEST, "advisories"))} files`);
