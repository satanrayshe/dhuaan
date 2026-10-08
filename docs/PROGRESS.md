# Dhuaan progress log (resume from here)

**Event:** Environmental Hacks. The clock opened **Thu 8 Oct 2026, 11:04 IST** (WeMakeDevs email). Submissions close Sun 11 Oct (exact time unpublished; target submitting by 16:00 IST).
**Plans:** `../prep/` (00-PLAYBOOK, 01-project-spec, 02-design-spec, 03-demo-video-script, 04-data-sources, 06-submission-guide). **Contracts:** `docs/CONTRACTS.md`.

## Done (Thu 8 Oct)
- 15:44 IST: repo created, `.env` gitignored, uv venv, contracts, config.py + store.py
- Phase 1 (workflow, about 46 min, 5 agents), committed per component:
  - model: 32 physics tests; 490 clusters × 5 members in about 17 s
  - ingest/geo/pipeline: FIRMS, Open-Meteo, LSA SAF, OpenAQ, districts, 3.5k receptors, HRSL population
  - agent/api: Strands, 7 tools, rules, grounding, advisories, Function URL API
  - infra: SAM template, layers (112 MB), deploy scripts, Amplify/S3 web deploy
  - web: Next.js 16, shadcn, mapcn, deck.gl, 6 routes, light + dark
- First live run 20261008T1100Z: 433 fires → 306 clusters, 20 s end to end. Top exposure comes from **Pakistani Punjab (Kasur/Pakpattan) → Firozpur/Fazilka**.
- Gemini: gemini-2.5-flash is retired for this key, so we use `gemini-flash-lite-latest` (set in .env).
- Flash-lite garbles Gurmukhi (it mixes in other scripts), so a strict script check now falls back to hand-written HI/PA templates.
- Telegram notify works: a real advisory was delivered to Shrey's chat.

## In progress
- Phase 2 workflow `wf_48070889-0b6`:
  - (a) backtest on 11 Nov 2025 (A vs B with GK2A afternoon fires), alpha calibration, afternoon_ratio.json, static industrial hotspot mask
  - (b) web on real data, India-only district filter, real BLH band, smaller trips.json, visual QA in light and dark
  - To resume: Workflow({scriptPath: "<session workflows dir>/dhuaan-phase2-wf_48070889-0b6.js", resumeFromRunId: "wf_48070889-0b6"}).

## Next
1. Commit phase 2 per component; re-run the pipeline; regenerate advisories.
2. Docs: README (hero GIF, architecture, AWS services table, method, backtest, limitations, credits, AI tools), docs/WRITEUP.md, docs/BLOG.md, video shot list updated to the real features.
3. **Deploy (needs Shrey):** `! aws login --region ap-south-1`, then `.\infra\deploy.ps1 -Web`. Then smoke-test /api/health, run the state machine once, and lock CORS with `-Origin`.
4. Create the GitHub repo under satanrayshe (private until Shrey says to make it public), then push.
5. Record footage per prep/03-demo-video-script.md.

## Blockers / needs Shrey
- `aws login` (the CLI session expired) for any deploy.
- Bedrock is blocked on the new account (support case "Bedrock allowlisting" open), so the agent runs on Gemini.
- Decision: making the GitHub repo public.
