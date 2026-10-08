# Demo video: final shot list (hard cap 2:55)

Adapted from `prep/03-demo-video-script.md` to what is actually built on 8 Oct 2026. Judges score the repo, video and write-up only, so the video has to show the product, who it's for and AWS (architecture plus real console evidence).

Rules for this cut:

- Every number on screen or in the voiceover must come from the run being recorded, `backend/out/latest/backtest.json`, `backend/data/facts.json` or a cited source. Values in [brackets] are from the 8 Oct 12:00 UTC run (`20261008T1200Z`) and **must be re-read from the screen on recording day**. If a value isn't on screen, cut the line.
- Never show replay data as live. The backtest is labelled "Backtest · Nov 2025" on screen.
- The agent runs on Gemini through Strands. Don't say "Nova" in the voiceover; say "Bedrock-ready".
- Captions on the whole time. Own voice; TTS only as a backup.

## Before recording

1. Run the pipeline in AWS within the last hour (`aws stepfunctions start-execution ...`, see `infra/README.md`) so the freshness chip is green and the Step Functions graph is fresh for the evidence shot.
2. Run the 06:30 advise path once (`{"mode":"advise"}`) so the demo school has a published advisory and a Telegram message exists on the phone.
3. Browser: clean profile, 1920×1080 or 4K, dark theme (top bar, theme toggle), no bookmarks bar, zoom 100%. Use `browser-video-recording` for zoom-follow on clicks.
4. Open these tabs in order: `/` · `/schools/?id=osm-w1090680897` · `/district/` · `/?place=dlw-21` · `/backtest/` · `/how-it-works/` · AWS console (ap-south-1): Step Functions `dhuaan-pipeline` latest execution, CloudWatch dashboard `dhuaan-ops`, Lambda function list filtered to `dhuaan`, S3 bucket `latest/`, EventBridge Scheduler schedules. Terminal with the last `sam deploy` output scrolled to "Successfully created/updated stack".
5. Dismiss the coach marks once on `/` (Skip), so they don't pop up mid-take; or keep them for the first shot only.

## Shot list

| Time | Beat | On screen (exact click path) | Voiceover |
|---|---|---|---|
| 0:00 to 0:12 | Hook | Title card, two lines appearing in turn: "Punjab farm fires, 2025: **5,114**" (source line: CityAirNews / MoEFCC). Then "**93%** of afternoon fire detections came after 4 pm" (source line: GK2A hourly detections, Jethva 2026, NASA GSFC, doi:10.5281/zenodo.20084790). | "Last season Punjab counted its fewest farm fires in years. But those counts come from satellites that pass at half past one. A geostationary satellite that watches all day saw 93 percent of the afternoon fires after 4 pm." |
| 0:12 to 0:17 | Title | Dhuaan · ਧੂੰਆਂ · धुआँ. "See the smoke before it reaches you." | (music hit) |
| 0:17 to 0:42 | The map | `/`. Press **Play** on the time scrubber (bottom). Particle trails flow east from the border fires. Hover the **Mixing height** band as it dips at night ("Under 300 m: smoke trapped"). Zoom (scroll) to Firozpur/Fazilka, then pull back to show the **ACROSS THE BORDER · Pakistani Punjab** label. | "Dhuaan takes every fire seen in the last two days and pushes its smoke through the next three days of winds, hour by hour, five times over. At night the air stops mixing and the smoke sits on the villages. Today most of it is coming from across the border." |
| 0:42 to 1:10 | Principal, Sangrur | Top bar **Schools** → the Bhawanigarh school is preselected (`/schools/?id=osm-w1090680897`). Show the 07:00 to 14:00 hour strip and its outdoors/limit/indoors labels. Click the **ਪੰਜਾਬੀ** tab, then **हिन्दी**, on the Parent notice. Zoom on the "[11/11] numbers verified" badge. Cut to the phone: the Telegram message from the Dhuaan bot (crop the chat header so no token or chat id is visible). | "Harpreet runs a school in Bhawanigarh. Every morning at 6:30 she gets tomorrow's plan, hour by hour: outdoors, short activity, or indoors, from the national air-quality bands. And a notice for parents in Punjabi, Hindi and English. Every number in it is checked against the forecast. If the model writes the wrong script, a hand-written template replaces it." |
| 1:10 to 1:25 | Ask Dhuaan | Back to `/`, press `/`, type "Bhawanigarh", pick the school. In the side card, click the suggested question "Should we keep tomorrow's morning assembly indoors?". Expand **How this was answered** to show the tool trace and the grounding badge. Use a real take; jump-cut the wait, don't speed it up. | "She can also just ask. The agent looks up the forecast with its tools, answers, and shows which numbers it verified." |
| 1:25 to 1:50 | District officer | Top bar **District**. Scope stays on **India only**. Hold on the headline: "[19] of [80] fire clusters in India cause [60]% of the smoke exposure from Indian fires over the next 48 h". Click row 1: the map flies to the cluster and draws where its smoke goes. Click **Export CSV**. Briefly switch scope to **Include across the border** to show the note "Fires across the border in Pakistani Punjab ([240] clusters) cause [85]% of all modelled exposure", then back. | "For the district team, Dhuaan ranks tonight's fires by people times hours of smoke downwind. A few clusters cause most of the harm, so a field team that can reach twenty fires can reach the right twenty. Fires across the border stay on the map, but off the list, because nobody here can act on them." |
| 1:50 to 2:00 | Delhi parent | Search (`/`) "Rohini" → pick "Rohini (ward 21, pre-2022)". Show **Smoke arrives**, the 72 h chart with its band, and **Where your air is from**. Tap **Share** ("Link copied"). | "In Delhi, any ward shows when smoke arrives and which districts it came from, with a link to share." |
| 2:00 to 2:20 | Proof, honestly | Top bar **Backtest**. Show the station chart (observed vs A vs B), then the skill tiles: hits [0/91] vs [1/91], Pearson r [0.13] vs [0.23]. Zoom on the Limitations text. | "Does it work? I fixed the test before running it: last November, held-out days, nine monitors. As an alarm, it barely works: one hit in ninety-one. Adding the afternoon fires does raise the correlation with real smoke, most in Delhi. The calibration is the weak link, and the page says so." |
| 2:20 to 2:45 | AWS | `/how-it-works/` architecture diagram (2 s), then 3 s each: Step Functions `dhuaan-pipeline` execution graph all green (Ingest → Model → Advise → Notify); CloudWatch `dhuaan-ops` dashboard; Lambda function list; EventBridge schedule "every 3 hours"; terminal `sam deploy` success. | "It all runs serverless on AWS in Mumbai. EventBridge starts a Step Functions pipeline every three hours. Lambda runs the smoke model and writes to S3, CloudFront serves the map, and Amplify hosts the site. The agent is built on Strands, on Gemini today and Bedrock-ready. One SAM template deploys it, on the Free plan." |
| 2:45 to 2:55 | Close | Wide map shot, playing. Overlay: live URL, github.com/satanrayshe/dhuaan, "Built solo by Shrey · Environmental Hacks 2026". | "Dhuaan. See the smoke before it reaches you." |

Spoken word count is about 390 words for 2:55, roughly 135 words a minute. Read it once against a timer before recording, and cut the Ask beat first if it runs long.

## Fallbacks

- No evening (LSA SAF) detections yet: don't show the **Split: midday vs evening** layer; it only appears when geostationary fires exist in the run. The 93% card carries that point instead.
- The demo school's plan says "Outdoors OK" all day (likely early in the season): keep it. Say "today it's clear" and move to the notice and badge. Don't fake a bad day.
- Agent slow or rate-limited: re-record the take or use a cached answer (the UI marks it "cached"). Don't hide real latency with speed ramps.
- If the AWS deploy isn't up by recording day, record the local build and show AWS evidence from the console only. Say nothing on camera that implies a live AWS URL.

## Description (YouTube, unlisted)

Title: "Dhuaan: stubble-smoke forecast on AWS | Environmental Hacks"

- Live: TODO · Repo: https://github.com/satanrayshe/dhuaan · Write-up: docs/WRITEUP.md
- AWS: EventBridge Scheduler, Step Functions, Lambda (+ Function URL, layers), S3, CloudFront, DynamoDB, SSM Parameter Store, Amplify Hosting, CloudWatch, SAM, AWS Open Data (HRSL, OpenAQ). Bedrock-ready via Strands.
- AI tools: Claude Code (development); Gemini via Strands Agents SDK (runtime).
- Data: NASA FIRMS, EUMETSAT LSA SAF, Open-Meteo (CC BY 4.0), OpenAQ, Meta/CIESIN HRSL, GK2A detections (NASA GSFC, Zenodo 10.5281/zenodo.20084790), geoBoundaries, GeoNames, OpenStreetMap contributors, DataMeet.
- Music: TODO (title, artist, licence).
