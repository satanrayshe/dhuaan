"""Small helpers shared by the infra scripts (no secrets are ever printed)."""
from __future__ import annotations

import os
from pathlib import Path

INFRA = Path(__file__).resolve().parent
REPO = INFRA.parent
STACK = os.environ.get("DHUAAN_STACK", "dhuaan")
REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "ap-south-1"


def session():
    import boto3
    return boto3.session.Session(region_name=REGION)


def stack_outputs(stack: str = STACK) -> dict[str, str]:
    cfn = session().client("cloudformation")
    st = cfn.describe_stacks(StackName=stack)["Stacks"][0]
    return {o["OutputKey"]: o["OutputValue"] for o in st.get("Outputs", [])}
