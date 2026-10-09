# Demo video: final cut (2:52)

The video is made and lives outside the repo, in `../video/` (see `../video/README.md`):

- `out/dhuaan-silent.mp4`: captions burned in, no voice
- `out/dhuaan-guide.mp4`: TTS timing guide and fallback
- `narration-script.md`: what Shrey reads
- `captions.srt`
- `mux.ps1`: Shrey's voice → `out/dhuaan-final.mp4`
- `out/thumbnail.png`

It was recorded on Fri 9 Oct 2026, 07:01–07:26 IST, from the live site (pipeline run `20261009T0100Z`, t0 06:30 IST) and real AWS evidence (execution `video-20261009T0131Z`, SUCCEEDED in 66.0 s).

Rules this cut follows:

- Every number on screen or in the voiceover comes from that run, `backend/out/latest/backtest.json` or `backend/data/facts.json`. The run is replaced every 3 h. If any beat is re-recorded, re-read its numbers from the screen and update `../video/tools/beats.py`.
- The backtest is labelled as last season's held-out days. The exploratory regional block is shown with its "not pre-registered" label.
- The agent runs on Gemini through Strands. The voiceover doesn't mention Nova. The architecture diagram says "Gemini / Bedrock Nova (MODEL_PROVIDER switch)".
- Captions are burned in for the whole video, and the `.srt` goes to YouTube too.
- The architecture shot is the live `/how-it-works/` page. `docs/architecture.svg` still shows a CloudFront box, which is not deployed, so the video doesn't use it.

## Final beat list

10 beats, 358 spoken words (about 125 wpm). The exact per-line timecodes are in `../video/narration-script.md` and `captions.srt`.

| Time | Beat | On screen | Voiceover |
|---|---|---|---|
| 0:00.0–0:12.0 | Hook: the afternoon gap | Rendered card: the 12:00-19:00 timeline, the ~13:30 VIIRS/MODIS pass marker, the 16:00+ bar filling, then 93% with the GK2A source line. | Punjab counts farm fires from satellites passing at half past one. A satellite watching all day saw 93% of afternoon fires after 4 pm, too late for that pass. |
| 0:12.0–0:19.5 | Title | Title card: Dhuaan · ਧੂੰਆਂ · धुआँ, 'See the smoke before it reaches you.', 'Stubble-smoke forecasts for Punjab, Haryana and Delhi · on AWS', then the audience row 'For: School heads · Parents · District field teams', over the dimmed live map. | This is Dhuaan. It means smoke. It's for schools, parents and district teams. |
| 0:19.5–0:43.5 | The map (dark theme, live run) | Live site, /. Play pressed on the time scrubber (0:22). Trails flow east from the border fires toward Haryana and Delhi. Cursor rests on the mixing-height band (0:31); camera eases onto the scrubber and its mixing-height band. Cursor moves to the ACROSS THE BORDER · Pakistani Punjab label (0:39). | Dhuaan takes every fire seen in the last two days, and pushes its smoke through the next three days of winds, five times over. Watch the band at the bottom. At night the air stops mixing, and smoke sits low over the villages. Right now, most of the modelled smoke comes from fires across the border. |
| 0:43.5–1:00.5 | Search and place card | Search 'Pakka', pick Pakka (Fazilka, Punjab). Map flies there; side card: 'No smoke arrival expected in the next 72 h', 'Highest, below alert level', the 72 h chart with the p10-p90 band. Card scrolls to 'Where your air is from': Okara · PK 66%, Pakpattan · PK 15%, Bahawalnagar · PK 7%, 'PK: across the border, Pakistani Punjab'. Camera eases onto the bars. | Search any village, school or Delhi ward. Pakka, near Fazilka, gets a 72-hour forecast. Today it stays below the alert level. Two-thirds of its smoke comes from Okara, across the border. |
| 1:00.5–1:19.5 | Ask Dhuaan (agent + tool trace + grounding) | Search 'Bhawanigarh', pick the Government Senior Secondary Boys School. Jump cut to the Ask Dhuaan box: click 'Should we keep tomorrow's morning assembly indoors?'. The live Lambda answer appears (marked 'cached': same question earlier in this run) with '7/7 numbers verified'; 'How this was answered · 1' opens to show get_school_day_plan(school_id=...). Camera eases onto the answer. | Say you run a school in Bhawanigarh, in Sangrur. You can just ask: should we keep the morning assembly indoors? The agent looks up the school's plan with a tool, answers, and shows its working, with every number checked. |
| 1:19.5–1:40.5 | School day planner + trilingual notice | /schools/?id=osm-w1090680897. 'Advisory for 9 Oct · Outdoors OK', hour strip 07:00-13:00, 'Daily 06:30 alert on Telegram' card. Scroll to Parent notice; tabs English -> ਪੰਜਾਬੀ (1:29) -> हिन्दी (1:34); cursor on '9/9 numbers verified' (1:38). Camera eases onto the notice. | The school gets the day's plan, hour by hour, from national air-quality bands. Today is clear: outdoors OK. The parent notice comes in English, Punjabi and Hindi. It goes to the school on Telegram, no app needed. Every number in it is checked: nine of nine. |
| 1:40.5–1:59.5 | District officer: India-only fire list | /district/, scope 'India only'. Headline: '11 of 39 fire clusters in India cause 63% of the smoke exposure from Indian fires over the next 48 h'; note: 'Fires across the border in Pakistani Punjab (133 clusters) cause 88% of all modelled exposure...'. Click row 1 (Ladhuka, Fazilka): map flies there and draws its smoke arcs. Click row 3 (Majitha, Amritsar). | For the district team, Dhuaan ranks fires by people times hours of smoke downwind. 11 of 39 clusters in India cause 63% of it. Click one to see where its smoke goes. Fires across the border stay on the map, off this list. |
| 1:59.5–2:19.5 | Backtest, honestly | /backtest/. Pre-registered skill tiles (held-out period): hit rate A 0% vs B 1% (0/91 vs 1/91), Pearson r 0.13 vs 0.23, R² -0.43 vs -0.41; camera eases onto the tiles. Scroll to the Delhi station charts, then the 'Exploratory - not pre-registered' block with Delhi/NCR Pearson r 0.40 vs 0.45. | Does it work? I fixed the test before running it: last November, nine monitors, held-out days. As an alarm, it barely works. One hit in 91. Afternoon fires lift correlation from 0.13 to 0.23. Better, still weak. |
| 2:19.5–2:45.5 | Where AWS fits (real evidence) | /how-it-works/ architecture: cursor on EventBridge Scheduler, AWS Step Functions, Amazon S3. Then the real AWS CLI scene (start-execution video-20261009T0131Z, describe-execution SUCCEEDED, lambda list-functions dhuaan-*, s3 ls latest/), the Step Functions graph rendered from that execution's history (Ingest 32.6 s, Model 18.7 s, Advise 12.1 s, Notify 2.5 s, total 66.0 s), and CloudWatch metric images (executions and Lambda invocations, last 11 h). | It all runs serverless on AWS in Mumbai, and Amplify hosts the site. EventBridge Scheduler starts a Step Functions pipeline every three hours. Lambda functions ingest, model, advise and notify, writing to S3. A real run this morning: 66 seconds, all green. CloudWatch watches it, and one SAM template deploys it all, on the Free plan. |
| 2:45.5–2:52.0 | Close | End card: Dhuaan · ਧੂੰਆਂ · धुआँ, live URL, github.com/satanrayshe/dhuaan, AWS service chips, 'Built solo by Shrey · WeMakeDevs × AWS Environmental Hacks 2026'. | Dhuaan. See the smoke before it reaches you. |

## Before submitting

- **Fix the API CORS** (duplicate `Access-Control-Allow-Origin`: Function URL `Cors` in `infra/template.yaml` plus `handler.py`). Until then, Ask Dhuaan shows "offline" to real visitors. For the Ask take only, the recording browser collapsed the duplicate header; the answer shown is the live Lambda response.
- Fix `advise_handler` for `{"mode":"advise"}`: the daily 06:30 run failed on 9 Oct with `KeyError: 'run_id'`. The voiceover says the notice "goes to the school on Telegram". It doesn't promise 06:30.
- The live `/api/ask` `get_school_day_plan` disagrees with the published advisory. At 08:17 IST it said "07:00–14:00, worst ~60 ug/m3" for osm-w1090680897, but `latest/advisories/osm-w1090680897.json` and the Schools page say 07:00–13:00 at 34 µg/m³. The cut keeps the consistent 07:19 take; see `../video/README.md` issue 5.
- The Ask take's question says "tomorrow's assembly", but it's answered with today's (9 Oct) plan. The voiceover avoids the word "tomorrow".

## Description (YouTube, unlisted)

Title: "Dhuaan: stubble-smoke forecast on AWS | Environmental Hacks"

- Live: https://main.d24aeuy7flk340.amplifyapp.com · Repo: https://github.com/satanrayshe/dhuaan · Write-up: docs/WRITEUP.md
- AWS:
  - EventBridge Scheduler
  - Step Functions
  - Lambda (with Function URL and layers)
  - S3
  - DynamoDB
  - SSM Parameter Store
  - Amplify Hosting
  - CloudWatch
  - SAM
  - AWS Open Data (HRSL, OpenAQ)
  - Bedrock-ready via Strands
- AI tools: Claude Code (development); Gemini via Strands Agents SDK (runtime).
- Data: NASA FIRMS, EUMETSAT LSA SAF, Open-Meteo (CC BY 4.0), OpenAQ, Meta/CIESIN HRSL, GK2A detections (NASA GSFC, Zenodo 10.5281/zenodo.20084790), geoBoundaries, GeoNames, OpenStreetMap contributors, DataMeet.
- Music: none.
- Chapters (YouTube needs each chapter to be at least 10 s long, so the title card is folded into the hook and the 6.5 s end card into the AWS chapter):
  - 0:00 Hook: the afternoon gap
  - 0:19 The map (dark theme, live run)
  - 0:43 Search and place card
  - 1:00 Ask Dhuaan (agent + tool trace + grounding)
  - 1:19 School day planner + trilingual notice
  - 1:40 District officer: India-only fire list
  - 1:59 Backtest, honestly
  - 2:19 Where AWS fits (real evidence)
