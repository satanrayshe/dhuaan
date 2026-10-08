#!/usr/bin/env bash
# One-command deploy of Dhuaan (Git Bash / Linux / macOS).
#   stage -> build_layers (if missing) -> sam build -> sam deploy -> put_secrets -> outputs
#   (writes web/.env.production) -> optional web build + deploy.
#
#   infra/deploy.sh                       # backend only
#   infra/deploy.sh --web                 # + Amplify Hosting
#   infra/deploy.sh --web --s3            # + S3/CloudFront fallback (site/)
#   infra/deploy.sh --origin https://main.d123.amplifyapp.com --rate-hours 6 --provider bedrock
set -euo pipefail
export SAM_CLI_TELEMETRY=0

INFRA="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$INFRA")"
BACKEND="$REPO/backend"

WEB=0; S3=0; REBUILD=0; SKIP_SECRETS=0; ORIGIN=""; RATE=""; PROVIDER=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --web) WEB=1 ;;
    --s3) S3=1 ;;
    --rebuild-layers) REBUILD=1 ;;
    --skip-secrets) SKIP_SECRETS=1 ;;
    --origin) ORIGIN="$2"; shift ;;
    --rate-hours) RATE="$2"; shift ;;
    --provider) PROVIDER="$2"; shift ;;
    -h|--help) sed -n 2,9p "$0"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

step() { printf '\n==> %s\n' "$*"; }
py() { uv run --project "$BACKEND" python "$@"; }

if command -v sam >/dev/null 2>&1; then SAM=sam
elif [[ -x "/c/Program Files/Amazon/AWSSAMCLI/bin/sam.cmd" ]]; then SAM="/c/Program Files/Amazon/AWSSAMCLI/bin/sam.cmd"
else echo "SAM CLI not found" >&2; exit 1; fi

step "Checking AWS credentials (aws login)"
aws sts get-caller-identity --query Arn --output text --region ap-south-1 || { echo "run 'aws login' first" >&2; exit 1; }

step "Staging Lambda code"
py "$INFRA/stage.py"

step "Building layers (skipped if present)"
if [[ $REBUILD == 1 ]]; then py "$INFRA/build_layers.py" --force; else py "$INFRA/build_layers.py"; fi

step "sam build"
(cd "$INFRA" && "$SAM" build)

step "sam deploy"
OVERRIDES=()
[[ -n "$ORIGIN" ]] && OVERRIDES+=("AllowedOrigin=$ORIGIN")
[[ -n "$RATE" ]] && OVERRIDES+=("PipelineRateHours=$RATE")
[[ -n "$PROVIDER" ]] && OVERRIDES+=("ModelProvider=$PROVIDER")
if [[ ${#OVERRIDES[@]} -gt 0 ]]; then
  (cd "$INFRA" && "$SAM" deploy --parameter-overrides "${OVERRIDES[@]}")
else
  (cd "$INFRA" && "$SAM" deploy)
fi

if [[ $SKIP_SECRETS == 0 ]]; then
  step "Writing secrets to SSM /dhuaan/*"
  py "$INFRA/put_secrets.py"
fi

step "Stack outputs -> web/.env.production"
py "$INFRA/outputs.py"

if [[ $WEB == 1 ]]; then
  step "Building web (static export)"
  (
    cd "$REPO/web"
    [[ $S3 == 1 ]] && export NEXT_PUBLIC_BASE_PATH=/site
    if [[ -f package-lock.json ]]; then npm ci; else npm install; fi
    npm run build
  )
  step "Deploying web"
  if [[ $S3 == 1 ]]; then py "$INFRA/deploy_web.py" --s3; else py "$INFRA/deploy_web.py"; fi
  echo "Tip: lock the API CORS to the web origin with: infra/deploy.sh --origin <WEB_URL origin>"
fi

printf '\nDone. Run the pipeline now: aws stepfunctions start-execution --state-machine-arn <StateMachineArn> --input "{}"\n'
