# The fires moved to 4 pm: a solo stubble-smoke forecast on AWS, for $0, in 72 hours

*By Shrey Sati (@shreysati). Built for the WeMakeDevs x AWS Environmental Hacks, 8 to 11 Oct 2026.*

Repo: TODO (github.com/satanrayshe/dhuaan) · Live site: TODO · Demo video: TODO

![Smoke trails from Punjab farm fires over the next 72 hours](img/hero.png)

## The number that started it

Punjab reported 5,114 farm fires between 15 September and 30 November 2025. In 2020 it was 83,002 ([CityAirNews](https://www.cityairnews.com/content/5114-farm-fires-reported-in-punjab-since-sep-15-mos-kirti-vardhan-singh)). If you only read the counts, the problem is nearly solved.

The counts come from NASA's polar-orbiting satellites, which cross Punjab around 13:30 IST. Researchers at NASA GSFC and Morgan State University have published a season of hourly fire detections from the Korean geostationary satellite GK2A, which watches the same fields all day ([Zenodo](https://doi.org/10.5281/zenodo.20084790), CC BY 4.0). I counted the Punjab detections between noon and 7 pm in October and November 2025. There were 33,074 of them, and 93% came at 4 pm or later, after the last polar pass.

So the fires didn't stop. A lot of them moved to the evening, where the official count can't see them. Evening is also the worst time to burn. After sunset the boundary layer, the slab of air that mixes near the ground, collapses from a kilometre or more to a few hundred metres. The smoke stays low and drifts into the villages next door. The first people to breathe it are kids in Sangrur and Bathinda, and nobody tells their principal at 6:30 am whether to hold assembly outside.

That became Dhuaan (ਧੂੰਆਂ, धुआँ, "smoke"): an hour-by-hour forecast of where farm-fire smoke goes, which fires matter most and what a school should do tomorrow.

## What I built in three days

I designed for three people. The personas are invented; the school is a real one in Bhawanigarh, Sangrur, taken from OpenStreetMap.

- A principal gets a 07:00 to 14:00 plan (outdoors OK, short light activity, or keep indoors) and a notice for parents in Punjabi, Hindi and English, sent to Telegram at 06:30.
- A district field officer gets tonight's fire clusters ranked by how many people-hours of smoke each will cause in the next 48 hours.
- A parent in Delhi searches their ward and sees when smoke arrives, how bad it gets and which districts sent it.

Under that is a small Lagrangian particle model in numpy. Each fire cluster releases particles in proportion to its fire radiative power. They ride the mixed-layer wind from Open-Meteo, take a random walk that grows with mixing depth, and decay over 48 hours. Concentration is the particle mass smoothed over 10 km and divided by the boundary-layer height, and that division is the whole night-time story in one line. Five ensemble members nudge wind speed, direction and diffusion, so every place gets a median and a band. Because each particle remembers which cluster it came from, attribution falls out exactly, and so does the exposure ranking: population times smoke times hours, with school cells weighted up during school hours.

The first live runs surprised me. On 8 October, 240 of the 320 fire clusters in my domain were across the border in Pakistani Punjab, and they accounted for 85% of all modelled exposure. For places in Indian Punjab, 73% of the population-weighted smoke forecast came from Kasur, Pakpattan and Okara, mostly reaching Firozpur, Fazilka and Muktsar. A district team can't do anything about those fires, so the fire list shows India only by default and the map labels the rest "across the border". The smoke stays on the map either way.

On top of the forecast sits a Strands agent with seven read-only tools over the forecast files. I don't trust a language model with numbers that a principal will forward to two hundred parents, so every number in an answer is checked against the tool results from that turn, in all three scripts (Devanagari and Gurmukhi digits included). The UI shows the count, for example "11/11 numbers verified", next to the tool trace.

## How it runs on AWS

Everything is one SAM template in ap-south-1:

- EventBridge Scheduler starts a Step Functions state machine every three hours: Ingest, Model, Advise, Notify, each a Lambda with its own retries. A second schedule runs Advise and Notify at 06:30 IST.
- The Model Lambda gets 3 GB and runs the ensemble in seconds. The 8 October run modelled 447 detections in 320 clusters in 3.75 s.
- Artifacts, including one JSON file per place, go to a private S3 bucket and out through CloudFront.
- The web app is a Next.js static export on Amplify Hosting, with deck.gl trails on a MapLibre map.
- The agent lives behind a Lambda Function URL. DynamoDB holds rate limits, SSM Parameter Store holds the keys, and CloudWatch holds a dashboard and the logs.
- Population (Meta's HRSL) and the backtest's PM2.5 history (OpenAQ) both come from AWS Open Data.

![Architecture](architecture.svg)

## Designing for the Free plan

My budget was zero, so every choice had to fit the AWS Free plan.

The map reads static JSON from CloudFront. There's no database query behind it, and CloudFront's always-free tier is far more than a demo needs. I used a Function URL instead of API Gateway. That saves a service, and it also removes the 30-second integration timeout, which matters when an agent makes several tool calls before answering.

Step Functions Standard gives 4,000 state transitions a month. One run is about six, so a three-hour schedule uses about 1,600. I set a floor of two hours on the schedule parameter so nobody can push it past the allowance by accident.

There are no containers, no VPC and no NAT gateway, because a NAT gateway costs money every hour it exists. The Lambdas are zip packages with two layers (numpy and friends, then Strands and the Gemini SDK), 112 MB together. They're built from manylinux wheels pinned to the lockfile, so no Docker is needed on Windows.

DynamoDB is on-demand with a TTL, SSM uses standard-tier SecureString parameters, and logs expire after 14 days. After judging I'll drop the schedule to six hours.

## What fought back

### Bedrock said no

My new account returned `ValidationException: Operation not allowed` when the agent called Bedrock. I opened a support case and kept going. The agent is built on the Strands Agents SDK, so the model sits behind a provider switch: today it runs on Gemini, and the IAM permission for Nova 2 Lite is already in the template. Moving to Bedrock is one stack parameter.

### Then Gemini moved under me

`gemini-2.5-flash` returned "no longer available to new users" on my key. I switched to `gemini-flash-lite-latest` and added a fallback chain of model ids that skips any model returning that error.

### Flash-lite can't spell Punjabi reliably

The Gurmukhi notices came back with characters from other scripts mixed in. Notices now go through a strict script check: every letter must be Gurmukhi (or Devanagari for Hindi) or plain ASCII for things like PM2.5 and school names. If a notice fails that or the number check, it is replaced by a hand-written template. In the first real advisory the English notice came from the model and the Hindi and Punjabi ones from templates, 11 of 11 numbers verified, and it arrived in my Telegram chat.

### Windows wouldn't run rasterio

Application Control on my laptop blocked the GDAL binaries. I needed population per 0.1° cell from HRSL's cloud-optimised GeoTIFFs on S3, so I wrote about a hundred lines of Python that parse the TIFF header, range-read only the full-resolution tiles over my domain, inflate them with zlib and sum the people.

### The map was too heavy

The first particle-trail file was about 15 MB. Capping trails at 3,000, keeping one point per hour (the browser interpolates) and rounding coordinates to three decimals took it to 3.4 MB, or 0.7 MB gzipped.

## Does it work?

I wrote the backtest protocol down before running it: one forecast per day at 05:30 IST from late October to 20 November 2025, scored at 12 to 35 hours of lead against nine government PM2.5 monitors, six in Punjab and three in Delhi. The calibration factor was fitted on 25 October to 5 November and every score is on 6 to 20 November, which the model never saw. Configuration A uses the polar satellite fires only. B adds the GK2A afternoon fires.

| Held out, 6 to 20 Nov 2025 | A | B |
|---|---|---|
| Smoke episodes hit (≥ 60 µg/m³ for 3 h) | 0 of 91 | 1 of 91 |
| Median lead time | n/a | 14 h |
| Pearson r, pooled | 0.13 | 0.23 |
| Pearson r, Punjabi Bagh, Delhi | 0.42 | 0.49 |

As an episode detector, this is close to no skill. The correlation moves the right way when the afternoon fires go in, at all three Delhi stations, and that's the part of my hypothesis the data supports. The reason for the zero is visible in the fit. One calibration factor is pooled across stations, and the Punjab monitors, close to fires where the model is noisy, drag it down to 0.16. Delhi alone would want something like 7 to 9, partly because Delhi's excess PM2.5 includes plenty of pollution that has nothing to do with farm fires. With the pooled factor, forecasts rarely cross 60 µg/m³, so they rarely "hit". The replayed weather archive is also slightly better than a live forecast, so even these numbers are an upper bound.

All of this is on the `/backtest` page. I'd rather a school knew how weak the forecast is than trusted it blindly.

## What's next

After the pre-registered run I tried one calibration factor per region, fitted on the same fit period. It's exploratory and I label it that way. Delhi then hits 57 of 57 episodes, which sounds great until you see that observed and forecast smoke both sit above 60 µg/m³ in 78% of those hours. A forecast that is high most of the time will hit most episodes. The live site uses the regional factors only as a provisional calibration.

Next come Bedrock Nova once the account is unblocked and a pilot with one real school. The evening-fire feed I use live, LSA SAF Meteosat-IODC, saw no fires in the domain on 8 October; the season is just starting, and I want to see what it catches in November.

## Credits

Built solo with Claude Code as my pair programmer, which wrote most of the code and tests while I made the design and physics calls. Data from NASA FIRMS, EUMETSAT LSA SAF, Open-Meteo, OpenAQ, Meta/CIESIN HRSL, NASA GSFC's GK2A detections (Jethva 2026), geoBoundaries, GeoNames, OpenStreetMap contributors and DataMeet; licences are listed in the repo.

Repo: TODO · Live site: TODO · Video: TODO
