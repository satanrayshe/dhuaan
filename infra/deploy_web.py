"""Deploy the static web export (web/out) without a Git connection.

Default: AWS Amplify Hosting manual deployment
  create app "dhuaan" + branch "main" if missing -> zip web/out -> create_deployment ->
  PUT the zip to the presigned URL -> start_deployment -> poll the job -> print the URL.
Fallback (--s3): upload web/out to s3://<BucketName>/site/ and print https://<cloudfront>/site/
  (use this if Amplify is not available on the Free plan; the web app must be built with basePath=/site).

    uv run --project backend python infra/deploy_web.py           # Amplify
    uv run --project backend python infra/deploy_web.py --s3      # S3 + CloudFront fallback
"""
from __future__ import annotations

import argparse
import io
import mimetypes
import sys
import time
import zipfile
from pathlib import Path

from _common import REPO, session, stack_outputs

OUT = REPO / "web" / "out"
for _ext, _type in {
    ".js": "application/javascript", ".mjs": "application/javascript", ".json": "application/json",
    ".geojson": "application/geo+json", ".css": "text/css", ".svg": "image/svg+xml",
    ".woff2": "font/woff2", ".txt": "text/plain", ".webmanifest": "application/manifest+json",
}.items():
    mimetypes.add_type(_type, _ext)


def files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def zip_out(root: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in files(root):
            z.write(p, p.relative_to(root).as_posix())  # index.html must sit at the zip root
    return buf.getvalue()


def paginate(client, op: str, key: str):
    token = None
    while True:
        resp = getattr(client, op)(**({"nextToken": token} if token else {}))
        yield from resp.get(key, [])
        token = resp.get("nextToken")
        if not token:
            return


def amplify(app_name: str, branch: str) -> int:
    import requests

    amp = session().client("amplify")
    app = next((a for a in paginate(amp, "list_apps", "apps") if a["name"] == app_name), None)
    if app is None:
        app = amp.create_app(
            name=app_name, platform="WEB", tags={"project": "dhuaan"},
            customRules=[{"source": "/<*>", "target": "/404.html", "status": "404-200"}],
        )["app"]
        print(f"deploy_web: created Amplify app {app['appId']}")
    app_id = app["appId"]
    try:
        amp.get_branch(appId=app_id, branchName=branch)
    except amp.exceptions.NotFoundException:
        amp.create_branch(appId=app_id, branchName=branch, stage="PRODUCTION", enableAutoBuild=False)
        print(f"deploy_web: created branch {branch}")

    blob = zip_out(OUT)
    print(f"deploy_web: zipped {len(files(OUT))} files ({len(blob) / 1e6:.1f} MB)")
    dep = amp.create_deployment(appId=app_id, branchName=branch)
    r = requests.put(dep["zipUploadUrl"], data=blob, headers={"Content-Type": "application/zip"}, timeout=300)
    r.raise_for_status()
    job_id = dep["jobId"]
    amp.start_deployment(appId=app_id, branchName=branch, jobId=job_id)
    status = "PENDING"
    for _ in range(120):  # up to 10 min
        status = amp.get_job(appId=app_id, branchName=branch, jobId=job_id)["job"]["summary"]["status"]
        if status in {"SUCCEED", "FAILED", "CANCELLED"}:
            break
        time.sleep(5)
    print(f"deploy_web: Amplify job {job_id}: {status}")
    if status != "SUCCEED":
        return 1
    print(f"WEB_URL=https://{branch}.{app_id}.amplifyapp.com")
    return 0


def cache_control(rel: str) -> str:
    if rel.startswith("_next/static/"):
        return "public, max-age=31536000, immutable"  # content-hashed
    return "public, max-age=60"


def s3_site(prefix: str) -> int:
    out = stack_outputs()
    bucket, base = out["BucketName"], out["DataBaseUrl"].rstrip("/")
    s3 = session().client("s3")
    fs = files(OUT)
    for p in fs:
        rel = p.relative_to(OUT).as_posix()
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        s3.upload_file(str(p), bucket, f"{prefix}/{rel}",
                       ExtraArgs={"ContentType": ctype, "CacheControl": cache_control(rel)})
    print(f"deploy_web: uploaded {len(fs)} files to s3://{bucket}/{prefix}/")
    dist = out.get("DistributionId")
    if dist:  # one wildcard path; 1,000 invalidation paths/month are free
        session().client("cloudfront").create_invalidation(
            DistributionId=dist,
            InvalidationBatch={"Paths": {"Quantity": 1, "Items": [f"/{prefix}/*"]},
                               "CallerReference": str(time.time())},
        )
    print(f"WEB_URL={base}/{prefix}/")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--s3", action="store_true", help="fallback: upload to the artifacts bucket under site/")
    ap.add_argument("--app", default="dhuaan")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--prefix", default="site")
    args = ap.parse_args()
    if not (OUT / "index.html").exists():
        print(f"deploy_web: {OUT / 'index.html'} not found - build the static export in web/ first",
              file=sys.stderr)
        return 1
    return s3_site(args.prefix.strip("/")) if args.s3 else amplify(args.app, args.branch)


if __name__ == "__main__":
    sys.exit(main())
