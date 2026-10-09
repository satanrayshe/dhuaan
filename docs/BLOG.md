# The fires moved to 4 pm: a solo stubble-smoke forecast on AWS, for $0, in 72 hours

**Subtitle (Builder Center "description" field):** Punjab's official farm-fire count fell to 5,114, but a geostationary satellite saw 93% of the afternoon fire detections after the counting satellites had passed. I built Dhuaan, a serverless smoke forecast that tells a school principal what tomorrow's air will be like, on the AWS Free plan.

**Tags:** AWS Lambda, AWS Step Functions, Amazon S3, Serverless, AWS SAM, Strands Agents, Sustainability, Hackathon

**Cover image:** `video/publish/img/cover-1600x900.png` (dark map: smoke trails from the 8 Oct 2026 run drifting across Punjab, with the "Across the border" label).

**Links:** Live site https://main.d24aeuy7flk340.amplifyapp.com · Repo TODO (github.com/satanrayshe/dhuaan) · Demo video TODO

---

*By Shrey Sati (@shreysati). Built solo for the WeMakeDevs x AWS Environmental Hacks, Air track, 8 to 11 October 2026.*

## The number that started it

Punjab recorded 5,114 farm fires between 15 September and 30 November 2025. That's 53% fewer than in 2024 and 93% fewer than in 2021, according to the Commission for Air Quality Management ([PIB, 1 Dec 2025](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2197201)). In 2020 the count was 83,002 ([The Tribune](https://www.tribuneindia.com/news/punjab/of-total-8404-farm-fire-cases-in-punjab-50-reported-in-past-2-weeks/amp)). Read only the counts and stubble burning looks nearly solved.

The counts come from polar-orbiting satellites that see the fields between about 10:30 am and 1:30 pm. Hiren Jethva at Morgan State University has published a season of hourly fire detections from the Korean geostationary satellite GK2A, which watches the same fields all afternoon ([Zenodo](https://doi.org/10.5281/zenodo.20084790), CC BY 4.0). I counted the Punjab detections between noon and 7 pm in October and November 2025. There were 33,074, and 93% of them came at 4 pm or later. iFOREST got to the same place another way: over 90% of large farm fires in Punjab in 2024 and 2025 happened after 3 pm ([The Tribune, 9 Dec 2025](https://www.tribuneindia.com/news/delhi/satellites-miss-majority-of-stubble-fires-delhi-air-pollution-underestimated-report/amp)).

So a lot of the burning moved to the evening, where the official count can't see it, and evening is the worst time to burn. After sunset the boundary layer, the slab of air that mixes near the ground, collapses from a kilometre or more to a few hundred metres, and the smoke stays low over the next village. The first people to breathe it are children in Sangrur and Bathinda, and nobody tells their principal at 6:30 am whether to hold assembly outside.

That became Dhuaan (ਧੂੰਆਂ, धुआँ, "smoke"): an hour-by-hour forecast of where farm-fire smoke goes, which fires do the most harm and what a school should do tomorrow.

## What I built in three days

I designed for three invented people. The school is real, in Bhawanigarh, Sangrur, taken from OpenStreetMap.

- A principal gets a 07:00 to 14:00 plan (outdoors OK, short light activity, or keep indoors) and a notice for parents in Punjabi, Hindi and English, sent to Telegram at 06:30.
- A district field officer gets tonight's fire clusters ranked by how many people-hours of smoke each will cause over the next 48 hours.
- A parent in Delhi searches their ward and sees when smoke arrives, how bad it gets and which districts sent it.

*[Image: `02-school-plan.png`, the school day planner with its hour strip and the "numbers verified" badge.]*

Under that is a small Lagrangian particle model in numpy. Each fire cluster releases particles in proportion to its fire radiative power, and they ride the mixed-layer wind from Open-Meteo with a random walk that grows with mixing depth. Concentration is the particle mass smoothed over 10 km and divided by the boundary-layer height, and that division is most of the night-time story. Five ensemble members nudge the wind and diffusion, so every place gets a median and a band. Each particle remembers its cluster, so attribution is exact, and so is the exposure ranking: population times smoke times hours, with schools weighted up during school hours.

The live runs surprised me. In the deployed run at 8:30 pm on 8 October, 289 of the 386 fire clusters in my domain were across the border in Pakistani Punjab, and they caused 87% of all modelled exposure. For the 893 places in Indian Punjab that you can search, at least three quarters of the forecast smoke over the next 48 hours came from across the border, mostly from Okara, Kasur and Pakpattan, and most of it landed in Fazilka. A district team can't act on those fires, so the fire list shows India only by default. On the Indian side, 30 of 97 clusters caused 61% of the exposure.

*[Image: `03-district-list.png`, "30 of 97 fire clusters in India cause 61%" with the ranked list and the map.]*

On top of the forecast sits a Strands agent with seven read-only tools over the forecast files. I don't trust a language model with numbers that a principal will forward to two hundred parents, so every number in an answer is checked against that turn's tool results, in all three scripts, Devanagari and Gurmukhi digits included. The UI shows the count next to the tool trace, for example "9/9 numbers verified" on the 9 October advisory.

## How it runs on AWS

Everything is one SAM template in ap-south-1 (Mumbai):

- EventBridge Scheduler starts a Step Functions state machine every three hours: Ingest, Model, Advise and Notify, each a Lambda with its own retries. A second schedule runs Advise and Notify at 06:30 IST.
- The Model Lambda gets 3 GB. The 8 October evening run tracked 561 detections in 386 clusters with 34,978 particles, and the ensemble took 15.7 seconds.
- Artifacts, including one JSON file per place, go to S3. The map reads them straight from the bucket.
- The web app is a Next.js static export on Amplify Hosting, with deck.gl trails on a MapLibre map.
- The agent sits behind a Lambda Function URL. DynamoDB holds rate limits, SSM Parameter Store holds the API keys, and a CloudWatch dashboard tracks runs, errors and API traffic.
- Population (Meta's HRSL) and the backtest's PM2.5 history (OpenAQ) come from AWS Open Data.

*[Image: `06-how-it-works.png`, the architecture page.]*

## Designing for the Free plan

My budget was zero, so every choice had to fit the AWS Free plan.

The map reads static JSON, so no database sits behind a page view. A Function URL replaces API Gateway, which removes its integration timeout of about 30 seconds, and that matters when an agent makes several tool calls before answering.

Step Functions Standard includes 4,000 state transitions a month. One run uses about six, so the three-hour schedule stays around 1,500. The schedule parameter has a floor of two hours so nobody can push it past the allowance by accident.

There are no containers, no VPC and no NAT gateway, which would bill for every hour it exists. The Lambdas are zip packages with two layers, 112 MB together, built from manylinux wheels so I didn't need Docker on Windows. DynamoDB is on-demand with a TTL and logs expire after 14 days. After judging I'll drop the schedule to six hours.

## What fought back

**Bedrock said no.** My new account returned `ValidationException: Operation not allowed` when the agent called Bedrock. I opened a support case and kept going. Because the agent is built on the Strands Agents SDK, the model sits behind a provider switch. It runs on Gemini today, the IAM permission for Nova 2 Lite is already in the template, and moving to Bedrock is one stack parameter.

**Then Gemini moved.** `gemini-2.5-flash` answered "no longer available to new users" on my key, so the agent now walks a fallback chain of model ids, starting with `gemini-flash-lite-latest`.

**Flash-lite can't spell Punjabi reliably.** The Gurmukhi notices came back with characters from other scripts mixed in. Every notice now goes through a strict script check: each letter must be Gurmukhi (or Devanagari for Hindi), or plain ASCII for things like PM2.5. A notice that fails this or the number check is replaced by a hand-written template. In the first advisory I generated, the English notice came from the model and the Hindi and Punjabi ones from templates, 11 of 11 numbers verified, and it reached my Telegram chat.

**I counted the same smoke twice.** School plans add forecast smoke to the latest measured PM2.5, but that measurement already contains the smoke present when it was taken. Plans now add only the change in smoke since then.

**The deploy rolled back.** My first `sam deploy` failed with "Your account must be verified before you can add new CloudFront resources." I made CloudFront an optional parameter and serve the artifacts straight from S3, with public read on three prefixes only. Then Windows PowerShell 5.1 killed my deploy script because SAM writes progress to stderr, so I deployed from Git Bash.

## Does it work?

I wrote the backtest protocol down before running it. One forecast a day at 05:30 IST from late October to 20 November 2025, scored at 12 to 35 hours of lead against nine government PM2.5 monitors, six in Punjab and three in Delhi. The calibration factor was fitted on 25 October to 5 November, and every score is on 6 to 20 November, which the model never saw. Configuration A uses the polar-satellite fires only. B adds the GK2A afternoon fires.

| Held out, 6 to 20 Nov 2025 | A | B |
|---|---|---|
| Smoke episodes hit (≥ 60 µg/m³ for 3 h) | 0 of 91 | 1 of 91 |
| Median lead time | n/a | 14 h |
| Pearson r, pooled | 0.13 | 0.23 |
| Pearson r, Punjabi Bagh, Delhi | 0.42 | 0.49 |

As an episode detector this is close to no skill. The correlation does move the right way when the afternoon fires go in, at all three Delhi stations, and that's the part of my hypothesis the data supports. The hit count is near zero because one calibration factor is pooled across stations, and the Punjab monitors, close to fires where the model is noisy, drag it down to 0.16. Delhi alone would want something like 7 to 9, partly because Delhi's excess PM2.5 includes plenty of pollution that has nothing to do with farm fires. With the pooled factor, forecasts rarely cross 60 µg/m³, so they rarely hit. The replayed weather archive is also a bit better than a live forecast, so treat even these numbers as an upper bound.

I'd rather a school knew how weak the forecast is than trusted it blindly.

## What's next

After the pre-registered run I tried one calibration factor per region, fitted on the same period, and I label it exploratory. Delhi then hits 57 of 57 episodes, which sounds great until you see that observed and forecast smoke both sit above 60 µg/m³ in 78% of those hours. A forecast that is high most of the time will hit most episodes. The pipeline uses the regional factors only as a provisional calibration, and every run's `meta.json` says which one it used.

Next: Bedrock Nova once the account is unblocked, and a pilot with one real school. The live evening-fire feed (LSA SAF Meteosat-IODC) saw no fires in the domain on 8 October, early in the season, and I want to see what it catches in November.

## Credits

Built solo, with Claude Code as my pair programmer. It wrote most of the code and tests while I made the design and physics calls. Data from NASA FIRMS, EUMETSAT LSA SAF, Open-Meteo, OpenAQ, Meta/CIESIN HRSL, the GK2A detections (Jethva 2026), geoBoundaries, GeoNames, OpenStreetMap contributors and DataMeet. Licences are listed in the repo.

Live site: https://main.d24aeuy7flk340.amplifyapp.com · Repo: TODO · Video: TODO
