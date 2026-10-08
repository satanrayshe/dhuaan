# Dhuaan: see the smoke before it reaches you

## Problem

Punjab's official farm-fire counts come from polar satellites that pass at about 13:30 IST, and the burning has moved later. Of 33,074 GK2A geostationary detections over Punjab between 12:00 and 18:59 IST in Oct to Nov 2025, 93% came at or after 16:00 (Jethva 2026, NASA GSFC, doi:10.5281/zenodo.20084790). Evening smoke settles into a shallow night layer, so the villages and schools beside the fields get it first.

## Who it's for

A school principal in Sangrur gets a 07:00 to 14:00 outdoor plan and a parent notice in Punjabi, Hindi and English on Telegram at 06:30. A district field officer gets tonight's fire clusters ranked by the people-hours of smoke they will cause, filtered to India and exportable as CSV. A Delhi parent can look up their ward and see when smoke arrives and which districts sent it. The personas are fictional.

## What I built

A 5-member Lagrangian smoke ensemble in numpy that tracks every fire cluster from the last 48 h through 72 h of forecast winds and divides by boundary-layer height, plus per-place attribution and a population-weighted exposure ranking. A Strands agent answers questions with 7 read-only tools, and a checker verifies every number in its answer against the tool output.

The backtest was pre-registered: daily forecasts for 6 to 20 Nov 2025 (held out), 9 monitors. A uses VIIRS/MODIS only; B adds GK2A afternoon fires. B hit 1 of 91 episodes against A's 0, and pooled correlation rose from 0.13 to 0.23 (all three Delhi stations improved). That is weak skill and I report it as weak: one pooled calibration factor, dominated by Punjab stations, keeps forecasts below the 60 µg/m³ episode threshold.

## How AWS is used

EventBridge Scheduler starts a Step Functions pipeline every 3 h and an advisory run at 06:30 IST. Lambda runs Ingest, Model (3 GB), Advise and Notify, plus an API behind a Lambda Function URL. S3 stores the artifacts, CloudFront serves them, and the Next.js static export is on Amplify Hosting. DynamoDB holds rate limits, SSM Parameter Store holds the API keys, and CloudWatch has the dashboard and logs. SAM deploys everything to ap-south-1, sized for the Free plan. The agent runs on the Strands Agents SDK with Gemini: Bedrock returned "Operation not allowed" on my new account (support case open), and Strands makes Nova a one-parameter switch that is already wired and permitted in IAM.

## What fought back

- Bedrock blocked, so I put a provider switch behind Strands. Then Google retired gemini-2.5-flash for new keys, so I added a fallback chain.
- Flash-lite garbled Gurmukhi by mixing scripts. A strict script check now swaps in hand-written Hindi and Punjabi templates.
- Windows Application Control blocked rasterio, so I wrote a small pure-Python COG reader that range-reads HRSL tiles from S3.
- trips.json started at about 15 MB; capping trips at 3,000, keeping one point per hour and rounding coordinates to 3 decimals brought it to 3.4 MB, or 0.7 MB gzipped.

## Limitations and next steps

The model sees fire smoke only, with one lumped removal rate and no plume rise. The live evening-fire feed (LSA SAF) had no detections in the domain on 8 Oct. An exploratory, not pre-registered, regional calibration hits 57 of 57 Delhi episodes, but observed and forecast smoke both sit above 60 µg/m³ in 78% of those hours, so I don't count it as skill. Next: Bedrock Nova once unblocked, and a pilot with one school.

## AI tools used

Claude Code wrote most of the code, tests and docs under my direction. Gemini (via Strands) runs the agent and notices at runtime.
