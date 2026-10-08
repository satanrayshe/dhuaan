# Dhuaan progress log (resume from here)

**Event:** Environmental Hacks. The clock opened **Thu 8 Oct 2026, 11:04 IST**. Submissions close Sun 11 Oct (exact time unpublished; target submitting by 16:00 IST).
**Plans:** `../prep/` (00-PLAYBOOK, 01-project-spec, 02-design-spec, 03-demo-video-script, 04-data-sources, 06-submission-guide). **Contracts:** `docs/CONTRACTS.md`. **Repo:** github.com/satanrayshe/dhuaan (private, in sync).

## State at Thu 8 Oct, 18:10 IST: built, tested locally, not deployed
- **Backend:** 191 pytest passing (`cd backend && uv run pytest -q`).
  - Live pipeline: `uv run python -m dhuaan.pipeline.run_local --members 5 --afternoon-mode observed`. About 20 s for 447 FIRMS fires (static hotspots masked), 320 clusters, Open-Meteo 540-pt grid, LSA SAF hourly, OpenAQ.
  - Model: Lagrangian, 5-member ensemble, attribution, exposure, trips, grid with blh_m.
  - Agent: Strands + Gemini (`gemini-flash-lite-latest` plus a live fallback chain), 7 tools, deterministic school rules, grounding check, trilingual advisories with a strict script check and HI/PA template fallback. Telegram notify works (sent to Shrey's chat).
  - API: Function URL handler plus local dev server `uv run python -m dhuaan.api.local` (:8787).
  - Backtest (`uv run python -m dhuaan.backtest.run [--reuse]`):
    - Pre-registered: hit rate A 0/91, B 1/91; r 0.13 / 0.23.
    - Exploratory regional calibration (clearly labelled; Delhi alpha 6.8 vs Punjab 0.149).
  - Facts: 93.0% of Punjab GK2A afternoon detections are at ≥16:00 IST.
- **Web:** `cd web && npm run data:sync && npm run build`. Next.js 16 static export with shadcn + mapcn + deck.gl, light (OpenAQ-inspired) + dark. Routes: `/`, `/place`, `/schools`, `/district`, `/backtest`, `/how-it-works`. Build and lint are clean.
- **Infra:** `infra/deploy.ps1 [-Web] [-S3] [-Origin <url>]` (SAM, layers 112 MB, Step Functions, Scheduler, CloudFront, DynamoDB, SSM, dashboard, Amplify deploy). Not yet deployed.
- **Docs:** README (TODO placeholders for the live URL, video, blog and hero image), docs/WRITEUP.md, docs/BLOG.md, docs/VIDEO.md, docs/method.md, docs/architecture.svg, LICENSE (MIT).

## Next (in order)
1. **Shrey:** `! aws login --region ap-south-1`.
2. Deploy: `.\infra\deploy.ps1 -Web`. If Amplify is blocked on the Free plan, use `-Web -S3`.
3. Smoke-test /api/health, start the state machine once, re-deploy with `-Origin <web url>` to lock CORS, then check the site in a private window.
4. Fill the README TODOs (live URL), capture docs/img/hero.png, and re-read the per-run numbers in docs/VIDEO.md.
5. **Shrey:** record the video (docs/VIDEO.md), voiceover, upload to YouTube (unlisted), publish the blog (docs/BLOG.md) on Builder Center as @shreysati.
6. **Shrey decides:** make the repo public, then submit (prep/06-submission-guide.md).

## Needs Shrey
- `aws login` (the CLI session expired).
- Bedrock is blocked on the new account (support case "Bedrock allowlisting"); the agent runs on Gemini. If AWS approves it, switch with `-Provider bedrock`.
- Verify the pitch numbers marked in README/WRITEUP: the 2025 Punjab fire counts (CityAirNews).
- Make the repo public (decision).
- Record the voiceover and publish the blog (only he can).

## Known limitations (stated in the docs)
- Weak pre-registered skill. The Delhi regional alpha mostly absorbs non-fire pollution.
- No LSA SAF afternoon detections yet this early in the season.
- Bijnor detections are not caught by the static mask.
- The web schools fallback plan doesn't apply the baseline smoke-delta fix (the backend advisory does).
