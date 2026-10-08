<#
.SYNOPSIS
  One-command deploy of Dhuaan (Windows PowerShell 5.1+).
  stage -> build_layers (if missing) -> sam build -> sam deploy -> put_secrets -> outputs
  (writes web/.env.production) -> optional web build + deploy.

.EXAMPLE
  .\infra\deploy.ps1                                   # backend only
  .\infra\deploy.ps1 -Web                              # + Amplify Hosting
  .\infra\deploy.ps1 -Web -S3                          # + S3/CloudFront fallback (site/)
  .\infra\deploy.ps1 -Origin https://main.d123.amplifyapp.com -RateHours 6
#>
param(
  [switch]$Web,
  [switch]$S3,
  [switch]$RebuildLayers,
  [switch]$SkipSecrets,
  [string]$Origin = "",
  [int]$RateHours = 0,
  [string]$Provider = ""
)
$ErrorActionPreference = "Stop"
$env:SAM_CLI_TELEMETRY = "0"
$Infra = $PSScriptRoot
$Repo = Split-Path $Infra -Parent
$Backend = Join-Path $Repo "backend"

function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Check($what) { if ($LASTEXITCODE -ne 0) { Write-Host "FAILED: $what (exit $LASTEXITCODE)" -ForegroundColor Red; exit 1 } }
function Py { & uv run --project $Backend python @args }

$Sam = (Get-Command sam -ErrorAction SilentlyContinue).Source
if (-not $Sam) { $Sam = "C:\Program Files\Amazon\AWSSAMCLI\bin\sam.cmd" }
if (-not (Test-Path $Sam)) { Write-Host "SAM CLI not found" -ForegroundColor Red; exit 1 }

Step "Checking AWS credentials (aws login)"
& aws sts get-caller-identity --query Arn --output text --region ap-south-1
Check "aws sts get-caller-identity - run 'aws login' first"

Step "Staging Lambda code"
Py (Join-Path $Infra "stage.py"); Check "stage"

Step "Building layers (skipped if present)"
if ($RebuildLayers) { Py (Join-Path $Infra "build_layers.py") --force } else { Py (Join-Path $Infra "build_layers.py") }
Check "build_layers"

Push-Location $Infra
try {
  Step "sam build"
  & $Sam build; Check "sam build"

  Step "sam deploy"
  $overrides = @()
  if ($Origin) { $overrides += "AllowedOrigin=$Origin" }
  if ($RateHours -gt 0) { $overrides += "PipelineRateHours=$RateHours" }
  if ($Provider) { $overrides += "ModelProvider=$Provider" }
  if ($overrides.Count -gt 0) { & $Sam deploy --parameter-overrides $overrides } else { & $Sam deploy }
  Check "sam deploy"
} finally { Pop-Location }

if (-not $SkipSecrets) {
  Step "Writing secrets to SSM /dhuaan/*"
  Py (Join-Path $Infra "put_secrets.py"); Check "put_secrets"
}

Step "Stack outputs -> web/.env.production"
Py (Join-Path $Infra "outputs.py"); Check "outputs"

if ($Web) {
  $WebDir = Join-Path $Repo "web"
  Step "Building web (static export)"
  Push-Location $WebDir
  try {
    if ($S3) { $env:NEXT_PUBLIC_BASE_PATH = "/site" }
    if (Test-Path "package-lock.json") { & npm ci } else { & npm install }
    Check "npm install"
    & npm run build; Check "npm run build"
  } finally { Pop-Location; Remove-Item Env:NEXT_PUBLIC_BASE_PATH -ErrorAction SilentlyContinue }

  Step "Deploying web"
  if ($S3) { Py (Join-Path $Infra "deploy_web.py") --s3 } else { Py (Join-Path $Infra "deploy_web.py") }
  Check "deploy_web"
  Write-Host "Tip: lock the API CORS to the web origin with  .\infra\deploy.ps1 -Origin <WEB_URL origin>" -ForegroundColor Yellow
}

Write-Host "`nDone. Run the pipeline now:  aws stepfunctions start-execution --state-machine-arn <StateMachineArn> --input '{}'" -ForegroundColor Green
