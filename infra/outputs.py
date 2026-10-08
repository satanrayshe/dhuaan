"""Print the dhuaan stack outputs and write web/.env.production for the static web build.

    uv run --project backend python infra/outputs.py            # print + write web/.env.production
    uv run --project backend python infra/outputs.py --no-write
"""
from __future__ import annotations

import argparse
import json
import sys

from _common import REPO, STACK, stack_outputs

ENV_FILE = REPO / "web" / ".env.production"


def env_production(out: dict[str, str]) -> str:
    data = out["DataBaseUrl"].rstrip("/")  # the web app appends /latest/<artifact> itself
    api = out["ApiUrl"].rstrip("/")
    return (
        "# Written by infra/outputs.py from the CloudFormation stack outputs. No secrets.\n"
        f"NEXT_PUBLIC_DATA_BASE={data}\n"
        f"NEXT_PUBLIC_API_BASE={api}\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        out = stack_outputs()
    except Exception as e:  # noqa: BLE001
        print(f"outputs: cannot read stack {STACK}: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        w = max(map(len, out)) if out else 0
        for k in sorted(out):
            print(f"  {k:<{w}}  {out[k]}")
    if not args.no_write:
        ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
        ENV_FILE.write_text(env_production(out), encoding="utf-8")
        print(f"outputs: wrote {ENV_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
