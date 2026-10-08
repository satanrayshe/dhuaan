"""Offline checks for infra/ (no AWS). Run: uv run --project backend pytest infra/tests -q"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from pathlib import Path

import pytest

INFRA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(INFRA))

yaml = pytest.importorskip("yaml")


class CfnLoader(yaml.SafeLoader):
    pass


def _any(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return {suffix: loader.construct_scalar(node)}
    if isinstance(node, yaml.SequenceNode):
        return {suffix: loader.construct_sequence(node, deep=True)}
    return {suffix: loader.construct_mapping(node, deep=True)}


CfnLoader.add_multi_constructor("!", _any)


@pytest.fixture(scope="module")
def tpl() -> dict:
    return yaml.load((INFRA / "template.yaml").read_text(encoding="utf-8"), Loader=CfnLoader)


def test_functions_contract(tpl):
    fns = {k: v["Properties"] for k, v in tpl["Resources"].items() if v["Type"] == "AWS::Serverless::Function"}
    expect = {
        "IngestFn": ("dhuaan.pipeline.handlers.ingest_handler", 900, 1024),
        "ModelFn": ("dhuaan.pipeline.handlers.model_handler", 900, 3008),
        "AdviseFn": ("dhuaan.pipeline.handlers.advise_handler", 300, 1024),
        "NotifyFn": ("dhuaan.pipeline.handlers.notify_handler", 60, 256),
        "ApiFn": ("dhuaan.api.handler.handler", 60, 1024),
    }
    assert set(fns) == set(expect)
    for name, (handler, timeout, mem) in expect.items():
        p = fns[name]
        assert (p["Handler"], p["Timeout"], p["MemorySize"]) == (handler, timeout, mem), name
        assert "ReservedConcurrentExecutions" not in p and "ProvisionedConcurrencyConfig" not in p
    assert fns["ApiFn"]["FunctionUrlConfig"]["AuthType"] == "NONE"
    g = tpl["Globals"]["Function"]
    assert g["Runtime"] == "python3.12" and g["Architectures"] == ["x86_64"] and g["CodeUri"] == ".stage/app"
    env = g["Environment"]["Variables"]
    for k in ("ARTIFACT_STORE", "ARTIFACT_BUCKET", "TABLE_NAME", "MODEL_PROVIDER", "GEMINI_MODEL",
              "BEDROCK_MODEL_ID", "SSM_PREFIX", "ALLOWED_ORIGIN"):
        assert k in env
    assert env["ARTIFACT_STORE"] == "s3" and env["SSM_PREFIX"] == "/dhuaan/"


def test_no_paid_footguns(tpl):
    types = {v["Type"] for v in tpl["Resources"].values()}
    banned = {"AWS::EC2::NatGateway", "AWS::EC2::VPC", "AWS::OpenSearchService::Domain",
              "AWS::SageMaker::Endpoint", "AWS::ECR::Repository"}
    assert not types & banned
    assert not any(t.startswith("AWS::BedrockAgentCore") for t in types)


def test_outputs(tpl):
    assert {"BucketName", "DataBaseUrl", "ApiUrl", "StateMachineArn", "DashboardUrl"} <= set(tpl["Outputs"])


def test_state_machine_substitutions(tpl):
    asl_text = (INFRA / "statemachine" / "pipeline.asl.json").read_text(encoding="utf-8")
    asl = json.loads(asl_text)
    used = set(re.findall(r"\$\{(\w+)\}", asl_text))
    subs = tpl["Resources"]["Pipeline"]["Properties"]["DefinitionSubstitutions"]
    assert used == set(subs)
    states = asl["States"]
    assert states["Ingest"]["Next"] == "Model" and states["Model"]["Next"] == "Advise"
    assert states["Advise"]["Next"] == "Notify" and states["Notify"]["Catch"]
    for s in ("Ingest", "Model", "Advise", "Notify"):
        assert states[s]["Retry"] and states[s]["Retry"][0]["BackoffRate"] >= 2


def test_schedules(tpl):
    ev = tpl["Resources"]["Pipeline"]["Properties"]["Events"]
    assert ev["DailyAdvisorySchedule"]["Properties"]["ScheduleExpression"] == "cron(0 1 * * ? *)"
    assert json.loads(ev["DailyAdvisorySchedule"]["Properties"]["Input"])["mode"] == "advise"
    assert "rate(" in str(ev["PipelineSchedule"]["Properties"]["ScheduleExpression"])


def test_stage_excludes_pycache():
    import stage
    out = stage.stage()
    assert (out / "dhuaan" / "__init__.py").exists() and (out / "data").is_dir()
    assert not list(out.rglob("__pycache__")) and not list(out.rglob("*.pyc"))
    assert not (out / "tests").exists() and not (out / "out").exists()


def test_env_production_and_zip(tmp_path):
    import deploy_web
    import outputs
    env = outputs.env_production({"DataBaseUrl": "https://d1.cloudfront.net", "ApiUrl": "https://x.lambda-url.ap-south-1.on.aws/"})
    assert "NEXT_PUBLIC_DATA_BASE=https://d1.cloudfront.net/latest\n" in env
    assert "NEXT_PUBLIC_API_BASE=https://x.lambda-url.ap-south-1.on.aws\n" in env
    (tmp_path / "_next").mkdir()
    (tmp_path / "index.html").write_text("x")
    (tmp_path / "_next" / "a.js").write_text("y")
    names = zipfile.ZipFile(io.BytesIO(deploy_web.zip_out(tmp_path))).namelist()
    assert sorted(names) == ["_next/a.js", "index.html"]


def test_put_secrets_keys_match_config():
    import put_secrets
    cfg = (INFRA.parent / "backend" / "dhuaan" / "config.py").read_text(encoding="utf-8")
    for k in put_secrets.SECRET_KEYS:
        assert f'"{k}"' in cfg


def test_layers_fit_if_built():
    build = INFRA / "layers" / "build"
    if not (build / "deps" / "python").is_dir():
        pytest.skip("layers not built (python infra/build_layers.py)")
    size = sum(f.stat().st_size for f in build.rglob("*") if f.is_file()) / 1e6
    assert size < 230, size
    agent = build / "agent" / "python"
    assert not (agent / "boto3").exists() and not (agent / "botocore").exists()
    assert (agent / "strands").is_dir() and (build / "deps" / "python" / "numpy").is_dir()
