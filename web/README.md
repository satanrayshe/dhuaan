# Dhuaan web

Next.js 16 (App Router, TypeScript) exported as a static site (`output: "export"`) for Amplify Hosting or S3 + CloudFront. UI: Tailwind v4, shadcn/ui (Radix), mapcn (MapLibre GL), deck.gl (TripsLayer, ScatterplotLayer, BitmapLayer through `MapboxOverlay`), Recharts through shadcn `chart`, next-themes, lucide.

## Run

```bash
npm install
node scripts/make-fixtures.mjs   # synthetic, schema-valid artifacts -> public/data/latest/
npm run dev                      # http://localhost:3000
npm run build                    # static export -> out/
npm run lint
```

## Data

Everything is fetched in the browser:

| What | URL |
|---|---|
| Artifacts 1-9 (docs/CONTRACTS.md) | `${NEXT_PUBLIC_DATA_BASE ?? "/data"}/latest/<artifact>` |
| API (`/api/health`, `/api/ask`, `/api/advisory`) | `${NEXT_PUBLIC_API_BASE ?? "http://localhost:8787"}` |

The typed models are in `src/lib/types.ts`. To use real pipeline output, copy `backend/out/latest/*` into `public/data/latest/` (or point `NEXT_PUBLIC_DATA_BASE` at the CloudFront origin; that origin then needs a CORS rule for the web origin). When `meta.json` has `"synthetic": true`, a "Sample data" badge appears.

The fixtures come from a small toy plume model in `scripts/make-fixtures.mjs`, so fires, trails, the smoke field, place series, attribution and exposure all agree with each other. It is not the Dhuaan model. Options: `--t0 2026-10-08T10:00:00Z --seed 7`.

Fallbacks: school advisories load from `advisories/<id>.json`, then `GET /api/advisory`, and finally from the same go/no-go rules applied in the browser (no notice text in that case). A missing `backtest.json` shows "Backtest pending". If the API is unreachable, the chat shows an offline message.

## Routes

`/` map · `/place/?id=` place view · `/schools/?id=` · `/district/` · `/backtest/` · `/how-it-works/`

Deep links for the demo recording: `?theme=dark|light`, `?lang=en|hi|pa`, and on `/`: `?place=<id>`, `?autoplay=1`, `?from=<hour -24..72>`, `?split=1` (midday vs evening comparison).

Keyboard: `⌘K`/`Ctrl K` or `/` opens search, `Space` plays or pauses, arrow keys move the time slider and the split handle.

## Colour

All data colours live in `src/lib/colors.ts`. They were checked with the dataviz palette validator against their surfaces in both themes: the smoke ramp (ordinal checks), the six NAQI categories (adjacent pairs; categories always carry a text label), and the backtest series (all pairs). The results are in the comment at the top of that file.

## Motion

With `prefers-reduced-motion`, the trails are off (and `trips.json` is never fetched), the smoke field steps hour by hour, and playback moves in whole hours. Playback pauses while the tab is hidden.
