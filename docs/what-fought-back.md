# What fought back

A running log of problems and fixes (feeds the writeup and blog).

- **8 Oct:** Bedrock returns `ValidationException: Operation not allowed` on the new Free-plan account. The agent runs on Strands behind a `MODEL_PROVIDER` switch (Gemini until Bedrock unblocks).
- **8 Oct:** A measured PM2.5 baseline already contains the smoke present when it was measured. Adding the forecast smoke on top, with the large provisional Delhi alpha (about 6.8), double-counted it. School plans now add only the change in smoke since the measurement.
- **8 Oct:** The first `sam deploy` rolled back: "Your account must be verified before you can add new CloudFront resources" (new-account restriction). CloudFront is now optional (`EnableCdn`), and artifacts are served straight from S3 with public read on `latest/`, `runs/` and `site/` only.
- **8 Oct:** Windows PowerShell 5.1 treats native stderr as an error, so `deploy.ps1` aborted on SAM progress output. Deployed from Git Bash instead.
- **8 Oct:** The API Lambda cold-started before the secrets were in SSM and cached empty values. Fixed by forcing a fresh container after `put_secrets`.
- **9 Oct:** Ask Dhuaan was offline in browsers even though curl worked. The Function URL CORS config and the handler both set Access-Control-Allow-Origin, and browsers reject a duplicated header. Fixed by removing the Function URL Cors block (the handler restricts to the site origin).
- **9 Oct:** The daily 06:30 IST advise-only run crashed with `KeyError: run_id` (its input has no run_id). It now advises on the latest published run.
- **9 Oct:** `backtest.json` lived only on the laptop, so live AWS runs were uncalibrated. It is now uploaded to S3 `latest/`.
- **9 Oct:** The chat agent and the Schools page could show different baselines for the same school. The agent now reuses the baseline the advisory step publishes in `latest/baselines.json`.
