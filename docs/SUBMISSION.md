# Submission answers (ready to paste)

For the WeMakeDevs x AWS Environmental Hacks form. The exact fields weren't published before the event, so each answer below is written to stand alone; paste whichever ones the form asks for. Fill the three TODO links first. Live-run numbers are from the deployed run of 8 Oct 2026, 20:30 IST (`20261008T1500Z`); backtest numbers are from `backend/out/latest/backtest.json`.

## Project name

Dhuaan (ਧੂੰਆਂ · धुआँ, "smoke")

## One-liner / tagline

See the smoke before it reaches you: an hour-by-hour stubble-smoke forecast for North India that ranks farm fires by the harm they do downwind and writes school advisories in Punjabi, Hindi and English.

## Track

Air

## Team

Solo: Shrey Sati (GitHub @satanrayshe, AWS Builder Center @shreysati).

## Links

- Repo: https://github.com/satanrayshe/dhuaan
- Live site (no login): https://main.d24aeuy7flk340.amplifyapp.com
- Demo video (YouTube, unlisted): https://youtu.be/ggdbMIAmj-Y
- Builder Center article: https://builder.aws.com/content/3KUc5XLFqOUJolBgu2tLP3mSexE/the-fires-moved-to-4-pm-a-solo-stubble-smoke-forecast-on-aws-for-dollar0-in-72-hours
- Live forecast data: https://dhuaan-artifactsbucket-oqallpjfrgta.s3.ap-south-1.amazonaws.com/latest/meta.json

## Problem (short)

Punjab recorded 5,114 farm fires between 15 Sep and 30 Nov 2025, 53% fewer than in 2024 (PIB / CAQM: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2197201). Those counts come from polar satellites that pass in the late morning and early afternoon, and the burning has moved later. Of 33,074 GK2A geostationary fire detections over Punjab between noon and 7 pm in Oct to Nov 2025, 93% came at or after 4 pm (Jethva 2026, https://doi.org/10.5281/zenodo.20084790). iFOREST found that over 90% of large Punjab fires in 2024 and 2025 happened after 3 pm (https://www.tribuneindia.com/news/delhi/satellites-miss-majority-of-stubble-fires-delhi-air-pollution-underestimated-report/amp). Evening smoke settles into a shallow night layer over the villages and schools next to the fields, and nobody tells a principal at 6:30 am whether to hold assembly outside.

## Solution (short)

Dhuaan takes every fire detected in the last 48 hours and runs its smoke through the next 72 hours of forecast winds with a 5-member Lagrangian particle ensemble. Each place gets an arrival time, a peak, a median with a p10 to p90 band, and a breakdown of which districts its smoke came from. Fire clusters are ranked by people-hours of smoke downwind, so a district team knows which fires matter. Schools get a 07:00 to 14:00 outdoor plan and a trilingual parent notice on Telegram at 06:30 IST. A Strands agent answers questions in three languages, and every number it writes is checked against its tool results before anyone sees it. A pre-registered backtest on November 2025 is published with its weak result.

## How AWS is used

- Amazon EventBridge Scheduler starts the pipeline every 3 h and an advisory run at 06:30 IST.
- AWS Step Functions (Standard) runs Ingest, Model, Advise and Notify with per-step retries.
- AWS Lambda runs those four steps (the Model function has 3 GB) plus the API; two Lambda layers hold numpy/h5py and the Strands + Gemini SDKs.
- A Lambda Function URL is the public HTTPS API (no API Gateway, so agent answers aren't cut off at about 30 s).
- Amazon S3 stores every run and serves the forecast JSON to the map. CloudFront is in the template as an option but is off, because new accounts can't create CloudFront resources yet.
- AWS Amplify Hosting serves the Next.js static site.
- Amazon DynamoDB (on-demand, TTL) holds API rate limits, subscriptions and the run index.
- AWS Systems Manager Parameter Store holds API keys as SecureString parameters.
- Amazon CloudWatch has the `dhuaan-ops` dashboard and 14-day logs.
- AWS SAM deploys the whole stack from one template to ap-south-1 (Mumbai), sized for the Free plan.
- AWS Open Data: HRSL population tiles and the OpenAQ archive for the backtest.
- Amazon Bedrock: Nova 2 Lite is wired and permitted in IAM, but Bedrock returned "Operation not allowed" on the new account (support case open). The agent runs on Google Gemini through the Strands Agents SDK; switching is one stack parameter.

## Tech stack

Python 3.12 (numpy, h5py, requests), Strands Agents SDK with Google Gemini (`gemini-flash-lite-latest` plus a fallback chain), AWS SAM, Next.js 16 static export with shadcn/ui, MapLibre and deck.gl, uv, pytest (200 tests). Data: NASA FIRMS, EUMETSAT LSA SAF, Open-Meteo, OpenAQ, Meta/CIESIN HRSL, GK2A hourly fire detections (Jethva 2026), geoBoundaries, GeoNames, OpenStreetMap, DataMeet.

## What fought back

- The first `sam deploy` rolled back: "Your account must be verified before you can add new CloudFront resources." CloudFront became optional and S3 serves the data directly.
- Bedrock returned "Operation not allowed" on the new account, so the agent runs on Gemini behind a Strands provider switch.
- Google retired `gemini-2.5-flash` for new keys, so the agent walks a fallback chain of model ids.
- Flash-lite mixed scripts in Gurmukhi. A strict script check swaps in hand-written Hindi and Punjabi templates.
- School plans counted the same smoke twice (forecast added to a baseline that already held it). They now add only the change since the measurement.
- Windows PowerShell 5.1 aborted the deploy on SAM's stderr output, so deploys run from Git Bash.

## AI tools used

- Claude Code (Anthropic) for development: it wrote most of the code, tests and docs under my direction. I made the design, physics and scope calls and checked the numbers.
- At runtime: Google Gemini through the Strands Agents SDK for the Ask Dhuaan agent and the parent notices. Amazon Bedrock Nova 2 Lite is ready behind the same switch.

## Writeup (about 590 words)

### Problem

Punjab recorded 5,114 farm fires between 15 Sep and 30 Nov 2025, 53% fewer than in 2024 ([PIB / CAQM](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2197201)). Those counts come from polar satellites that pass in the late morning and early afternoon. The burning has moved later. Of 33,074 GK2A geostationary detections over Punjab between 12:00 and 18:59 IST in Oct to Nov 2025, 93% came at or after 16:00 ([Jethva 2026, doi:10.5281/zenodo.20084790](https://doi.org/10.5281/zenodo.20084790)). iFOREST found the same pattern: over 90% of large Punjab fires in 2024 and 2025 happened after 3 pm ([The Tribune](https://www.tribuneindia.com/news/delhi/satellites-miss-majority-of-stubble-fires-delhi-air-pollution-underestimated-report/amp)). Evening smoke settles into a shallow night layer, and the schools beside the fields breathe it first.

### Who it's for

A school principal in Sangrur gets a 07:00 to 14:00 outdoor plan and a parent notice in Punjabi, Hindi and English on Telegram at 06:30. A district field officer gets tonight's fire clusters ranked by the people-hours of smoke they will cause. A Delhi parent can look up their ward and see when smoke arrives and which districts sent it. The personas are fictional.

### What I built

A 5-member Lagrangian smoke ensemble in numpy carries every fire cluster from the last 48 h through 72 h of forecast winds, with per-place attribution and a population-weighted exposure ranking. In the deployed run of 8 Oct, 20:30 IST, 30 of 97 Indian clusters caused 61% of the exposure from Indian fires. A Strands agent answers questions with 7 read-only tools, and a checker verifies every number in its answer against the tool output.

The backtest was pre-registered: daily forecasts scored on held-out days (6 to 20 Nov 2025) at 9 monitors. A uses VIIRS/MODIS only; B adds GK2A afternoon fires. B hit 1 of 91 episodes against A's 0, and pooled correlation rose from 0.13 to 0.23, with all three Delhi stations improving. That is weak skill. One pooled calibration factor, dominated by Punjab stations, keeps forecasts below the 60 µg/m³ episode threshold.

### How AWS is used

EventBridge Scheduler starts a Step Functions pipeline every 3 h and an advisory run at 06:30 IST. Lambda runs Ingest, Model (3 GB), Advise and Notify, plus an API behind a Lambda Function URL. S3 stores the artifacts and serves them to the map, and the Next.js static export is on Amplify Hosting. DynamoDB holds rate limits, SSM Parameter Store holds the API keys, and CloudWatch has the dashboard and logs. SAM deploys it all to ap-south-1 on the Free plan. The agent runs on Gemini through the Strands Agents SDK, because Bedrock returned "Operation not allowed" on my new account (support case open). Nova is one stack parameter away and already permitted in IAM.

### What fought back

- The first deploy rolled back because new accounts can't create CloudFront resources. CloudFront became optional and S3 serves the data directly.
- Google retired gemini-2.5-flash for new keys, so the agent walks a fallback chain of model ids.
- Flash-lite mixed scripts in Gurmukhi. A strict script check now swaps in hand-written Hindi and Punjabi templates.
- Adding forecast smoke to a measured baseline counted the same smoke twice. School plans now add only the change since the measurement.

### Limitations and next steps

The model sees fire smoke only, with one lumped removal rate and no plume rise. The live evening-fire feed (LSA SAF) had no detections in the domain on 8 Oct. Next: Bedrock Nova once unblocked, and a pilot with one school.

### AI tools used

Claude Code wrote most of the code, tests and docs under my direction. Gemini (via Strands) runs the agent and notices at runtime.

## Sources for every external number

| Claim | Source |
|---|---|
| Punjab 5,114 and Haryana 662 farm fires, 2025, window 15 Sep to 30 Nov (ISRO protocol); Punjab 53% below 2024, 86% below 2023, 93% below 2021 | PIB / CAQM press release, 1 Dec 2025: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2197201 |
| Punjab 10,909 in 2024 | All India Radio News, 26 Feb 2026: https://www.newsonair.gov.in/punjab-53-decline-in-stubble-burning-recorded-during-kharif-season-2025 (also ETV Bharat citing MoEFCC, 20 Dec 2025: https://www.etvbharat.com/en/bharat/stubble-burning-incidents-fell-drastically-in-northern-states-govt-data-enn25122004270) |
| Punjab 83,002 in 2020 (and 36,663 in 2023) | The Tribune, 18 Nov 2024: https://www.tribuneindia.com/news/punjab/of-total-8404-farm-fire-cases-in-punjab-50-reported-in-past-2-weeks/amp. ETV Bharat's MoEFCC table gives 36,650 for 2023, so the 2023 figure is not used. |
| Polar passes observe between 10:30 and 13:30; over 90% of large Punjab fires in 2024 and 2025 after 3 pm | iFOREST Stubble Burning Status Report 2025, via The Tribune, 9 Dec 2025: https://www.tribuneindia.com/news/delhi/satellites-miss-majority-of-stubble-fires-delhi-air-pollution-underestimated-report/amp |
| 93% of 33,074 GK2A detections (12:00 to 18:59 IST, Oct to Nov 2025) at or after 16:00 | Computed in `backend/data/facts.json` from Jethva 2026, Morgan State University, Zenodo, CC BY 4.0: https://doi.org/10.5281/zenodo.20084790 |
| Delhi AQI 425 at 9 am on 11 Nov 2025; CAQM invoked GRAP Stage III (backtest episode date) | PIB, 11 Nov 2025: https://www.pib.gov.in/PressReleasePage.aspx?PRID=2188873. The prep notes said 428; I could not confirm that from a primary source, so use 425 at 9 am if the date comes up. |
| Stubble share of Delhi PM2.5, 1 Oct to 30 Nov 2025: about 4.2% on average, briefly over 22% in mid-November | CSE, 31 Dec 2025: https://www.cseindia.org/beyond-the-burn-delhi-s-winter-smog-intensifies-even-after-stubble-fires-fade-12982. Not used in the docs. If you use it, cite CSE and the period, because other analyses use different windows and get different averages. |
