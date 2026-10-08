"""Settings: read from the repo-root .env locally, or from env vars plus SSM /dhuaan/* in Lambda."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"

DOMAIN = {"lon_min": 72.5, "lon_max": 79.0, "lat_min": 28.0, "lat_max": 32.75}
SECRET_KEYS = (
    "FIRMS_MAP_KEY", "OPENAQ_API_KEY", "GEMINI_API_KEY", "DATA_GOV_IN_API_KEY",
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "LSASAF_USERNAME", "LSASAF_PASSWORD",
)


def _load_env() -> None:
    env_file = REPO_DIR / ".env"
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)
    # In Lambda, secrets live in SSM Parameter Store under /dhuaan/<KEY>.
    if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") and os.environ.get("SSM_PREFIX", "/dhuaan/"):
        missing = [k for k in SECRET_KEYS if not os.environ.get(k)]
        if missing:
            import boto3
            ssm = boto3.client("ssm")
            prefix = os.environ.get("SSM_PREFIX", "/dhuaan/")
            names = [prefix + k for k in missing]
            for i in range(0, len(names), 10):
                resp = ssm.get_parameters(Names=names[i:i + 10], WithDecryption=True)
                for p in resp.get("Parameters", []):
                    os.environ.setdefault(p["Name"].removeprefix(prefix), p["Value"])


_load_env()


@dataclass(frozen=True)
class Settings:
    firms_map_key: str = field(default_factory=lambda: os.environ.get("FIRMS_MAP_KEY", ""))
    openaq_api_key: str = field(default_factory=lambda: os.environ.get("OPENAQ_API_KEY", ""))
    gemini_api_key: str = field(default_factory=lambda: os.environ.get("GEMINI_API_KEY", ""))
    data_gov_in_api_key: str = field(default_factory=lambda: os.environ.get("DATA_GOV_IN_API_KEY", ""))
    telegram_bot_token: str = field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.environ.get("TELEGRAM_CHAT_ID", ""))
    lsasaf_username: str = field(default_factory=lambda: os.environ.get("LSASAF_USERNAME", ""))
    lsasaf_password: str = field(default_factory=lambda: os.environ.get("LSASAF_PASSWORD", ""))
    model_provider: str = field(default_factory=lambda: os.environ.get("MODEL_PROVIDER", "gemini"))
    gemini_model: str = field(default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"))
    bedrock_model_id: str = field(default_factory=lambda: os.environ.get("BEDROCK_MODEL_ID", "global.amazon.nova-2-lite-v1:0"))
    aws_region: str = field(default_factory=lambda: os.environ.get("AWS_REGION", "ap-south-1"))
    artifact_store: str = field(default_factory=lambda: os.environ.get("ARTIFACT_STORE", "local"))
    artifact_bucket: str = field(default_factory=lambda: os.environ.get("ARTIFACT_BUCKET", ""))
    local_out: Path = field(default_factory=lambda: Path(os.environ.get("LOCAL_OUT", str(BACKEND_DIR / "out"))))
    cache_dir: Path = field(default_factory=lambda: Path(os.environ.get("CACHE_DIR", "/tmp/dhuaan-cache" if os.environ.get("AWS_LAMBDA_FUNCTION_NAME") else str(BACKEND_DIR / "cache"))))
    table_name: str = field(default_factory=lambda: os.environ.get("TABLE_NAME", ""))
    allowed_origin: str = field(default_factory=lambda: os.environ.get("ALLOWED_ORIGIN", "*"))


settings = Settings()
