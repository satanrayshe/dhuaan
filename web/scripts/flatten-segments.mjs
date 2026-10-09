// Post-build fix for the static export's client-side prefetch files.
// The Next 16 client fetches segment data as dot-joined filenames
// (convertSegmentPathToStaticExportFilename: `__next${segmentPath.replace(/\//g, ".")}.txt`,
// e.g. /schools/__next.schools.__PAGE__.txt), but the export writes them as nested
// folders on this machine (/schools/__next.schools/__PAGE__.txt). Every prefetch then 404s
// and link navigation falls back to full page loads. Copy each nested file to the flat name.
import fs from "node:fs";
import path from "node:path";

const OUT = path.resolve(import.meta.dirname, "..", "out");
let copied = 0;

function flatten(dir, prefix, parent) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    const name = `${prefix}.${e.name}`;
    if (e.isDirectory()) flatten(p, name, parent);
    else if (e.name.endsWith(".txt")) {
      const dest = path.join(parent, name);
      if (!fs.existsSync(dest)) {
        fs.copyFileSync(p, dest);
        copied++;
      }
    }
  }
}

function walk(dir) {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (!e.isDirectory() || e.name === "_next" || e.name === "data") continue;
    const p = path.join(dir, e.name);
    if (e.name.startsWith("__next.")) flatten(p, e.name, dir);
    else walk(p);
  }
}

if (fs.existsSync(OUT)) {
  walk(OUT);
  console.log(`flatten-segments: wrote ${copied} flat segment files`);
}
