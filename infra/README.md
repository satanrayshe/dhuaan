# Dhuaan infrastructure (AWS SAM, ap-south-1)

Everything runs serverless in **ap-south-1 (Mumbai)** and is sized for the **AWS Free plan**. It uses zip Lambdas with two prebuilt layers. There are no containers, no VPC or NAT, no provisioned or reserved concurrency, and no always-on compute.

## Architecture

```
                      EventBridge Scheduler
        every N h (PipelineRateHours, default 3)     daily 06:30 IST = cron(0 1 * * ? *) UTC
                 {"mode":"full"}                          {"mode":"advise"}
                        |                                       |
                        v                                       v
   +--------------------- Step Functions (Standard) "dhuaan-pipeline" ----------------------+
   |  Route --full--> Ingest ------> Model -------> Advise ------> Notify --(catch)--> Done |
   |    |            (Lambda 900s   (Lambda 900s   (Lambda 300s   (Lambda 60s              |
   |    |             1 GB)          3 GB)          1 GB)          256 MB, optional)       |
   |    +--advise-------------------------------------^                                    |
   |  per-step retries with exponential backoff + jitter; a Notify failure never fails a run|
   +----------------------------------------------------------------------------------------+
          |                 |                  |               |
          |  NASA FIRMS     |  numpy ensemble  |  Strands      |  Telegram Bot API
          |  Open-Meteo     |  (5 members)     |  agent        |
          |  LSA SAF/OpenAQ |                  |  (Gemini now, |
          v                 v                  |  Bedrock Nova |
   +------------------------------------+      |  by config)   |
   |  S3 artifacts bucket (private)     |<-----+               |
   |  latest/  runs/<run_id>/  raw/     |                      |
   |  advisories/   site/ (fallback)    |      DynamoDB "pk/sk" (on-demand, TTL "ttl"):
   +------------------------------------+      rate-limit counters, subscriptions, run index
          | OAC (SigV4)
          v
   CloudFront (HTTPS, gzip/brotli, honours Cache-Control, CORS *)
          |                                           SSM Parameter Store /dhuaan/*
          v                                           (SecureString, aws/ssm key): API keys
   Browser: Next.js static export  <----------------  read by each Lambda at cold start
   on Amplify Hosting (or CloudFront /site/)
          |
          |  POST /api/ask, GET /api/search, /api/advisory, /api/health
          v
   Lambda Function URL (AuthType NONE, CORS = AllowedOrigin) -> ApiFn (60 s, 1 GB): agent + places API
                                                                 (no API Gateway, so no 30 s cap)

   CloudWatch: dashboard "dhuaan-ops" (executions, failures, durations, errors, API traffic), logs kept 14 days
```

### What each AWS service does

| Service | Role in Dhuaan |
|---|---|
| **EventBridge Scheduler** | Starts the pipeline every `PipelineRateHours` (default 3) and runs Advise + Notify every day at 06:30 IST, before school starts. |
| **AWS Step Functions** (Standard) | Runs Ingest → Model → Advise → Notify with per-step retries and backoff. It's the pipeline graph shown in the demo. One run is about 6 state transitions. |
| **AWS Lambda** (python3.12, x86_64) | `ingest` pulls fires (NASA FIRMS VIIRS/MODIS, LSA SAF geostationary), winds and boundary-layer height (Open-Meteo) and PM2.5 (OpenAQ). `model` runs the 5-member Lagrangian smoke ensemble in numpy and writes the map artifacts. `advise` runs the Strands agent that writes school advisories in English, Hindi and Punjabi. `notify` sends Telegram alerts. `api` serves the chat agent and place search. |
| **Lambda layers** | `dhuaan-deps` (numpy, h5py, requests, dotenv) and `dhuaan-agent` (Strands + Gemini SDK). Both are built from manylinux wheels, so the build works on Windows with no Docker. |
| **Lambda Function URL** | A public HTTPS endpoint for `/api/*`. There's no API Gateway, so agent answers can take longer than 30 s. |
| **Amazon S3** | Private artifact store: `latest/` (what the map reads), `runs/<run_id>/` (history, expires after 30 days), `raw/` (expires after 14 days), and `site/` for the hosting fallback. |
| **Amazon CloudFront** | Serves the artifacts over HTTPS from Indian edge locations. It reads S3 through Origin Access Control, compresses responses, honours `Cache-Control` (5 min for `latest/`, 1 day for `runs/`) and adds `Access-Control-Allow-Origin: *`. |
| **Amazon DynamoDB** | Single table (`pk`, `sk`, TTL `ttl`, on-demand billing). Holds the API rate-limit counters (20 asks per IP per hour, 500 per day overall), subscriptions and the run index. |
| **AWS Systems Manager Parameter Store** | Holds the secrets (`/dhuaan/FIRMS_MAP_KEY`, `GEMINI_API_KEY`, ...) as SecureString parameters, encrypted with the AWS-managed `aws/ssm` key. |
| **Amazon Bedrock** | IAM permission is already granted (Nova 2 Lite through the global inference profile). Switching from Gemini is one parameter: `ModelProvider=bedrock`. |
| **AWS Amplify Hosting** | Hosts the Next.js static export as a manual zip deploy with no Git connection. |
| **Amazon CloudWatch** | The `dhuaan-ops` dashboard, plus Lambda logs kept for 14 days. |

## Files

| File | Purpose |
|---|---|
| `template.yaml` | The SAM template, containing every resource above. |
| `statemachine/pipeline.asl.json` | The pipeline definition (ARNs are filled in through `DefinitionSubstitutions`). |
| `samconfig.toml` | Stack `dhuaan`, ap-south-1, `CAPABILITY_IAM`, `resolve_s3`, no changeset prompt. |
| `stage.py` | Copies `backend/dhuaan` and `backend/data` into `infra/.stage/app`, the CodeUri for every function. Tests, out, cache and `__pycache__` never ship. |
| `build_layers.py` | Builds `layers/build/{deps,agent}/python` from manylinux_2_34 x86_64 wheels pinned to `backend/uv.lock`. It strips tests and `__pycache__` and checks the 250 MB limit. |
| `put_secrets.py` | Copies `.env` secrets to SSM `/dhuaan/<KEY>` as SecureString. Values are never printed. `--dry-run` lists the parameter names. |
| `outputs.py` | Prints the stack outputs and writes `web/.env.production`. |
| `deploy_web.py` | Deploys `web/out` to Amplify. `--s3` uploads to `s3://<bucket>/site/` behind CloudFront instead. |
| `deploy.ps1` / `deploy.sh` | One command that runs every step above in order. |
| `tests/test_infra.py` | Offline checks: template contract, ASL, staging, layers. |

## Deploy

Prerequisites: AWS CLI v2 signed in (`aws login`), SAM CLI ≥ 1.120, uv, and Node 20+ (only for the web step).

```powershell
# from the repo root, Windows
.\infra\deploy.ps1                 # backend: stage, layers, sam build/deploy, secrets, outputs
.\infra\deploy.ps1 -Web            # also builds web/ and deploys it to Amplify Hosting
.\infra\deploy.ps1 -Web -S3        # fallback: web on CloudFront under /site/
.\infra\deploy.ps1 -Origin https://main.<appid>.amplifyapp.com   # lock API CORS to the site
```
```bash
infra/deploy.sh [--web] [--s3] [--origin URL] [--rate-hours 6] [--provider bedrock] [--rebuild-layers] [--skip-secrets]
```

The same steps by hand, if you need to run one alone:
```bash
python infra/stage.py
python infra/build_layers.py            # ~15 s; --force rebuilds
cd infra && sam build && sam deploy && cd ..
uv run --project backend python infra/put_secrets.py
uv run --project backend python infra/outputs.py      # writes web/.env.production
aws stepfunctions start-execution --state-machine-arn <StateMachineArn> --input '{}'   # run now
```

`web/.env.production` (generated):
```
NEXT_PUBLIC_DATA_BASE=https://<id>.cloudfront.net/latest
NEXT_PUBLIC_API_BASE=https://<id>.lambda-url.ap-south-1.on.aws
```

Stack parameters: `PipelineRateHours` (2–24, default 3), `ScheduleState` (ENABLED/DISABLED), `AllowedOrigin` (default `*`), `ModelProvider` (gemini/bedrock), `GeminiModel`, `BedrockModelId`.

Layer sizes, measured 8 Oct: deps 66 MB and agent 46 MB unzipped, so 112 MB for ApiFn and AdviseFn, which attach both. The Lambda limit is 250 MB.

## Cost on the Free plan (rough monthly figures at the default 3 h rate)

| Item | Usage | Free allowance |
|---|---|---|
| Step Functions | about 250 full runs × ~6 transitions + 31 advise-only runs × ~4 ≈ 1,600 transitions | 4,000 per month. `PipelineRateHours` has a minimum of 2 so this can't be exceeded. |
| Lambda compute | Model 3 GB × ~2 min × 250 ≈ 90k GB-s, all functions ≈ 150k GB-s | 400k GB-s and 1M requests |
| EventBridge Scheduler | about 280 invocations | 14M |
| CloudFront | well under 1 GB transfer for a demo | 1 TB and 10M requests (always free); CloudFront Functions 2M |
| S3 | a few hundred MB (`runs/` expires after 30 days, `raw/` after 14) | 5 GB. PUT requests are the one thing to watch: writing every `places/<id>.json` twice per run can pass 2,000 PUTs a month. That's still cents, and it's covered by Free plan credits. |
| DynamoDB on-demand | a few thousand requests | 25 GB storage is free. On-demand requests cost about $1.25 per million and are covered by credits. |
| SSM Parameter Store | 8 standard SecureString parameters | Free (standard tier; the `aws/ssm` KMS key is free) |
| CloudWatch | 1 dashboard, AWS metrics, logs kept 14 days | 3 dashboards, 5 GB of logs |
| Amplify Hosting | one small static site | Build minutes aren't used (it's a manual zip deploy); 15 GB served per month |
| Bedrock | Not used while `ModelProvider=gemini` | The Gemini API free tier is outside AWS |

After submission, run `deploy.ps1 -RateHours 6`, or set `ScheduleState=DISABLED` to pause both schedules and keep everything else.

## Teardown

```bash
aws s3 rm s3://<BucketName> --recursive          # CloudFormation can't delete a bucket that isn't empty
cd infra && sam delete --stack-name dhuaan --region ap-south-1 --no-prompts
aws ssm delete-parameters --names $(aws ssm get-parameters-by-path --path /dhuaan/ --query "Parameters[].Name" --output text)
aws amplify delete-app --app-id <appid>          # if the web app was deployed to Amplify
```
The log groups and layer versions are deleted with the stack. SAM leaves its own `aws-sam-cli-managed-default` bucket behind, which holds the deployment zips. Empty it and delete that stack too if you want nothing left.

## Contract for the handlers (INGEST / AGENT)

- Each Step Functions task passes the previous step's return value as the next step's `event` (`OutputPath: $.Payload`). Handlers must return a **small JSON object** (a dict, under 256 KB), for example `{"run_id": ..., "t0_utc": ...}`. The real data travels through S3.
- `ingest_handler` receives `{"mode": "full", "trigger": "schedule"}`, or `{}` on a manual run. `advise_handler` receives either the Model output or `{"mode": "advise", "trigger": "daily"}` and should use `latest/`.
- `notify_handler` is optional. If it raises, the run still succeeds, and the error is stored at `$.notify_error`.
- Lambda reads secrets from SSM at cold start (`dhuaan/config.py`). The env vars it gets are `ARTIFACT_STORE=s3`, `ARTIFACT_BUCKET`, `TABLE_NAME`, `MODEL_PROVIDER`, `GEMINI_MODEL`, `BEDROCK_MODEL_ID`, `SSM_PREFIX=/dhuaan/`, `ALLOWED_ORIGIN` and `DATA_BASE_URL`. `/tmp` is the default 512 MB.
- The Function URL handles CORS, including preflight, for `AllowedOrigin`. Configure CORS in only one place: when `AWS_LAMBDA_FUNCTION_NAME` is set, the API handler should not add its own `Access-Control-Allow-*` headers, because they can collide with the URL's.
