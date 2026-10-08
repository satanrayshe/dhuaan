"""Copy the secret keys from the repo-root .env into SSM Parameter Store as SecureString (standard tier).

    /dhuaan/<KEY>   for each key in SECRET_KEYS that has a non-empty value in .env

Lambdas read them at cold start (dhuaan/config.py, ssm:GetParameters WithDecryption) with the
AWS-managed aws/ssm KMS key, so this costs nothing on the Free plan. Values are never printed.

    uv run --project backend python infra/put_secrets.py --dry-run   # names only, no AWS calls
    uv run --project backend python infra/put_secrets.py
"""
from __future__ import annotations

import argparse
import sys

from dotenv import dotenv_values

from _common import REGION, REPO

# Must match CONTRACTS.md "Environment" and dhuaan.config.SECRET_KEYS.
SECRET_KEYS = (
    "FIRMS_MAP_KEY", "OPENAQ_API_KEY", "GEMINI_API_KEY", "DATA_GOV_IN_API_KEY",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "LSASAF_USERNAME", "LSASAF_PASSWORD",
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="list parameter names only")
    ap.add_argument("--prefix", default="/dhuaan/")
    ap.add_argument("--env-file", default=str(REPO / ".env"))
    args = ap.parse_args()

    values = dotenv_values(args.env_file)
    present = [k for k in SECRET_KEYS if (values.get(k) or "").strip()]
    missing = [k for k in SECRET_KEYS if k not in present]
    print(f"put_secrets: {len(present)}/{len(SECRET_KEYS)} secrets set in {args.env_file} (region {REGION})")
    if missing:
        print("put_secrets: empty or missing (skipped): " + ", ".join(missing))
    if args.dry_run:
        for k in present:
            print(f"  would write SecureString {args.prefix}{k}")
        return 0

    from _common import session
    ssm = session().client("ssm")
    failed = 0
    for k in present:
        name = args.prefix + k
        try:
            ssm.put_parameter(Name=name, Value=values[k].strip(), Type="SecureString",
                              Tier="Standard", Overwrite=True, Description="dhuaan secret (from .env)")
            print(f"  wrote {name}")
        except Exception as e:  # noqa: BLE001 - report name + error class only, never the value
            failed += 1
            print(f"  FAILED {name}: {type(e).__name__}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
