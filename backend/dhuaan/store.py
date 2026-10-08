"""Artifact store: JSON/bytes under a key, backed by a local directory or S3.

Keys look like "latest/meta.json" or "runs/<run_id>/places/<id>.json".
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any, Protocol

from dhuaan.config import settings


class Store(Protocol):
    def put_json(self, key: str, obj: Any) -> None: ...
    def get_json(self, key: str) -> Any | None: ...
    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None: ...
    def get_bytes(self, key: str) -> bytes | None: ...
    def exists(self, key: str) -> bool: ...


def _dumps(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


class LocalStore:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root or settings.local_out)

    def _path(self, key: str) -> Path:
        p = self.root / key
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def put_json(self, key: str, obj: Any) -> None:
        self._path(key).write_bytes(_dumps(obj))

    def get_json(self, key: str) -> Any | None:
        p = self.root / key
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self._path(key).write_bytes(data)

    def get_bytes(self, key: str) -> bytes | None:
        p = self.root / key
        return p.read_bytes() if p.exists() else None

    def exists(self, key: str) -> bool:
        return (self.root / key).exists()


class S3Store:
    """JSON objects are stored gzip-encoded with Content-Encoding so CloudFront/browsers decode them transparently."""

    def __init__(self, bucket: str | None = None):
        import boto3
        self.bucket = bucket or settings.artifact_bucket
        self.s3 = boto3.client("s3", region_name=settings.aws_region)

    def put_json(self, key: str, obj: Any) -> None:
        self.s3.put_object(
            Bucket=self.bucket, Key=key, Body=gzip.compress(_dumps(obj)),
            ContentType="application/json", ContentEncoding="gzip",
            CacheControl="public, max-age=300" if key.startswith("latest/") else "public, max-age=86400",
        )

    def get_json(self, key: str) -> Any | None:
        data = self.get_bytes(key)
        return json.loads(data) if data is not None else None

    def put_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
        self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get_bytes(self, key: str) -> bytes | None:
        try:
            obj = self.s3.get_object(Bucket=self.bucket, Key=key)
        except self.s3.exceptions.NoSuchKey:
            return None
        body = obj["Body"].read()
        return gzip.decompress(body) if obj.get("ContentEncoding") == "gzip" else body

    def exists(self, key: str) -> bool:
        try:
            self.s3.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False


def get_store() -> Store:
    return S3Store() if settings.artifact_store == "s3" else LocalStore()
