"""Ask rate limits: 20 per IP per hour and 500 per day globally.

In memory locally; DynamoDB atomic counters with TTL when settings.table_name is set.
Table (infra/template.yaml): pk (S, HASH) + sk (S, RANGE), TTL attribute `ttl`. Items:
  {pk: "ratelimit#ask#ip#<sha256(ip)[:16]>", sk: "<YYYYMMDDHH UTC>"} and {pk: "ratelimit#ask#all", sk: "<YYYYMMDD UTC>"},
  counter attribute `n` (Number).
IPs are stored hashed, never raw.
"""
from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import dataclass
from typing import Protocol

from dhuaan.config import settings

PER_IP_HOUR = 20
GLOBAL_DAY = 500


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str = ""
    retry_after_s: int = 0


class Limiter(Protocol):
    def check(self, ip: str) -> Decision: ...


def _ip_key(ip: str) -> str:
    return hashlib.sha256((ip or "unknown").encode()).hexdigest()[:16]


def _windows(now: float) -> tuple[str, str, int, int]:
    t = time.gmtime(now)
    hour = time.strftime("%Y%m%d%H", t)
    day = time.strftime("%Y%m%d", t)
    secs_to_hour = 3600 - (t.tm_min * 60 + t.tm_sec)
    secs_to_day = 86400 - (t.tm_hour * 3600 + t.tm_min * 60 + t.tm_sec)
    return hour, day, secs_to_hour, secs_to_day


class MemoryLimiter:
    def __init__(self, per_ip_hour: int = PER_IP_HOUR, global_day: int = GLOBAL_DAY, clock=time.time):
        self.per_ip_hour, self.global_day, self.clock = per_ip_hour, global_day, clock
        self._counts: dict[str, int] = {}
        self._lock = threading.Lock()

    def check(self, ip: str) -> Decision:
        hour, day, to_hour, to_day = _windows(self.clock())
        kip, kall = f"ip#{_ip_key(ip)}#{hour}", f"all#{day}"
        with self._lock:
            # drop old windows
            for k in [k for k in self._counts if not (k.endswith(hour) or k.endswith(day))]:
                del self._counts[k]
            if self._counts.get(kip, 0) >= self.per_ip_hour:
                return Decision(False, f"limit of {self.per_ip_hour} questions per hour reached", to_hour)
            if self._counts.get(kall, 0) >= self.global_day:
                return Decision(False, f"daily limit of {self.global_day} questions reached for everyone", to_day)
            self._counts[kip] = self._counts.get(kip, 0) + 1
            self._counts[kall] = self._counts.get(kall, 0) + 1
        return Decision(True)


class DynamoLimiter:
    def __init__(self, table_name: str, per_ip_hour: int = PER_IP_HOUR, global_day: int = GLOBAL_DAY,
                 client=None, clock=time.time):
        if client is None:
            import boto3
            client = boto3.client("dynamodb", region_name=settings.aws_region)
        self.table, self.client, self.clock = table_name, client, clock
        self.per_ip_hour, self.global_day = per_ip_hour, global_day

    def _incr(self, pk: str, sk: str, limit: int, ttl: int) -> bool:
        try:
            self.client.update_item(
                TableName=self.table, Key={"pk": {"S": pk}, "sk": {"S": sk}},
                UpdateExpression="ADD n :one SET #ttl = if_not_exists(#ttl, :ttl)",
                ConditionExpression="attribute_not_exists(n) OR n < :limit",
                ExpressionAttributeNames={"#ttl": "ttl"},
                ExpressionAttributeValues={":one": {"N": "1"}, ":limit": {"N": str(limit)}, ":ttl": {"N": str(ttl)}},
            )
            return True
        except Exception as e:
            if type(e).__name__ == "ConditionalCheckFailedException" or "ConditionalCheckFailed" in str(e):
                return False
            raise

    def check(self, ip: str) -> Decision:
        now = self.clock()
        hour, day, to_hour, to_day = _windows(now)
        if not self._incr(f"ratelimit#ask#ip#{_ip_key(ip)}", hour, self.per_ip_hour, int(now) + to_hour + 3600):
            return Decision(False, f"limit of {self.per_ip_hour} questions per hour reached", to_hour)
        if not self._incr("ratelimit#ask#all", day, self.global_day, int(now) + to_day + 86400):
            return Decision(False, f"daily limit of {self.global_day} questions reached for everyone", to_day)
        return Decision(True)


_limiter: Limiter | None = None


def get_limiter() -> Limiter:
    global _limiter
    if _limiter is None:
        _limiter = DynamoLimiter(settings.table_name) if settings.table_name else MemoryLimiter()
    return _limiter


def set_limiter(limiter: Limiter | None) -> None:
    global _limiter
    _limiter = limiter
