# Dhuaan: see the smoke before it reaches you

## Problem

Punjab recorded 5,114 farm fires between 15 Sep and 30 Nov 2025, 53% fewer than in 2024 ([PIB / CAQM](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2197201)). Those counts come from polar satellites that pass in the late morning and early afternoon. The burning has moved later. Of 33,074 GK2A geostationary detections over Punjab between 12:00 and 18:59 IST in Oct to Nov 2025, 93% came at or after 16:00 ([Jethva 2026, doi:10.5281/zenodo.20084790](https://doi.org/10.5281/zenodo.20084790)). iFOREST found the same pattern: over 90% of large Punjab fires in 2024 and 2025 happened after 3 pm ([The Tribune](https://www.tribuneindia.com/news/delhi/satellites-miss-majority-of-stubble-fires-delhi-air-pollution-underestimated-report/amp)). Evening smoke settles into a shallow night layer, and the schools beside the fields breathe it first.

## Who it's for

A school principal in Sangrur gets a 07:00 to 14:00 outdoor plan and a parent notice in Punjabi, Hindi and English on Telegram at 06:30. A district field officer gets tonight's fire clusters ranked by the people-hours of smoke they will cause. A Delhi parent can look up their ward and see when smoke arrives and which districts sent it. The personas are fictional.

## What I built

A 5-member Lagrangian smoke ensemble in numpy carries every fire cluster from the last 48 h through 72 h of forecast winds, with per-place attribution and a population-weighted exposure ranking. In the deployed run of 8 Oct, 20:30 IST, 30 of 97 Indian clusters caused 61% of the exposure from Indian fires. A Strands agent answers questions with 7 read-only tools, and a checker verifies every number in its answer against the tool output.

The backtest was pre-registered: daily forecasts scored on held-out days (6 to 20 Nov 2025) at 9 monitors. A uses VIIRS/MODIS only; B adds GK2A afternoon fires. B hit 1 of 91 episodes against A's 0, and pooled correlation rose from 0.13 to 0.23, with all three Delhi stations improving. That is weak skill. One pooled calibration factor, dominated by Punjab stations, keeps forecasts below the 60 µg/m³ episode threshold.

## How AWS is used

EventBridge Scheduler starts a Step Functions pipeline every 3 h and an advisory run at 06:30 IST. Lambda runs Ingest, Model (3 GB), Advise and Notify, plus an API behind a Lambda Function URL. S3 stores the artifacts and serves them to the map, and the Next.js static export is on Amplify Hosting. DynamoDB holds rate limits, SSM Parameter Store holds the API keys, and CloudWatch has the dashboard and logs. SAM deploys it all to ap-south-1 on the Free plan. The agent runs on Gemini through the Strands Agents SDK, because Bedrock returned "Operation not allowed" on my new account (support case open). Nova is one stack parameter away and already permitted in IAM.

## What fought back

- The first deploy rolled back because new accounts can't create CloudFront resources. CloudFront became optional and S3 serves the data directly.
- Google retired gemini-2.5-flash for new keys, so the agent walks a fallback chain of model ids.
- Flash-lite mixed scripts in Gurmukhi. A strict script check now swaps in hand-written Hindi and Punjabi templates.
- Adding forecast smoke to a measured baseline counted the same smoke twice. School plans now add only the change since the measurement.

## Limitations and next steps

The model sees fire smoke only, with one lumped removal rate and no plume rise. The live evening-fire feed (LSA SAF) had no detections in the domain on 8 Oct. Next: Bedrock Nova once unblocked, and a pilot with one school.

## AI tools used

Claude Code wrote most of the code, tests and docs under my direction. Gemini (via Strands) runs the agent and notices at runtime.
