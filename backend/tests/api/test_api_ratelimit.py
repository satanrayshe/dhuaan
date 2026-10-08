from __future__ import annotations

from dhuaan.api.ratelimit import DynamoLimiter, MemoryLimiter


def test_memory_limiter_windows():
    t = [1_760_000_000.0]
    lim = MemoryLimiter(per_ip_hour=2, global_day=3, clock=lambda: t[0])
    assert lim.check("a").allowed and lim.check("a").allowed
    d = lim.check("a")
    assert not d.allowed and 0 < d.retry_after_s <= 3600
    assert lim.check("b").allowed
    d = lim.check("c")
    assert not d.allowed and "daily" in d.reason
    t[0] += 86400
    assert lim.check("a").allowed


class FakeDynamo:
    class ConditionalCheckFailedException(Exception):
        pass

    def __init__(self):
        self.items: dict[str, dict] = {}

    def update_item(self, TableName, Key, UpdateExpression, ConditionExpression, ExpressionAttributeNames,
                    ExpressionAttributeValues):
        assert set(Key) == {"pk", "sk"}
        pk = Key["pk"]["S"] + "|" + Key["sk"]["S"]
        it = self.items.get(pk)
        limit = int(ExpressionAttributeValues[":limit"]["N"])
        if it is not None and it["n"] >= limit:
            raise FakeDynamo.ConditionalCheckFailedException("The conditional request failed")
        if it is None:
            it = self.items[pk] = {"n": 0, "ttl": int(ExpressionAttributeValues[":ttl"]["N"])}
        it["n"] += 1


def test_dynamo_limiter_atomic_counters_and_ttl():
    fake = FakeDynamo()
    now = 1_760_000_000.0
    lim = DynamoLimiter("t", per_ip_hour=2, global_day=3, client=fake, clock=lambda: now)
    assert lim.check("1.1.1.1").allowed and lim.check("1.1.1.1").allowed
    assert not lim.check("1.1.1.1").allowed
    assert lim.check("2.2.2.2").allowed
    assert not lim.check("3.3.3.3").allowed
    keys = list(fake.items)
    assert any(k.startswith("ratelimit#ask#ip#") for k in keys) and any(k.startswith("ratelimit#ask#all|") for k in keys)
    assert all("1.1.1.1" not in k for k in keys)  # IPs are hashed
    assert all(v["ttl"] > now for v in fake.items.values())
