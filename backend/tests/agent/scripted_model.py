"""Scripted Strands model for tests (no network)."""
from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from strands.models import Model


class ScriptedModel(Model):
    """Replays a script of turns. Each turn is either {"tools": [(name, args), ...]} or {"text": "..."}."""

    def __init__(self, turns: list[dict]):
        self.turns = list(turns)
        self.requests: list[Any] = []
        self.config: dict = {"model_id": "scripted"}

    def update_config(self, **model_config: Any) -> None:
        self.config.update(model_config)

    def get_config(self) -> Any:
        return self.config

    async def structured_output(self, output_model, prompt, system_prompt=None, **kwargs):  # pragma: no cover
        raise NotImplementedError
        yield {}

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs) -> AsyncGenerator[dict, None]:
        self.requests.append({"messages": messages, "system_prompt": system_prompt,
                              "tools": [t["name"] for t in (tool_specs or [])]})
        turn = self.turns.pop(0) if self.turns else {"text": "(script exhausted)"}
        yield {"messageStart": {"role": "assistant"}}
        if "tools" in turn:
            for i, (name, args) in enumerate(turn["tools"]):
                yield {"contentBlockStart": {"start": {"toolUse": {"name": name, "toolUseId": f"t{len(self.requests)}_{i}"}}}}
                yield {"contentBlockDelta": {"delta": {"toolUse": {"input": json.dumps(args)}}}}
                yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
        else:
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": turn["text"]}}}
            yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "end_turn"}}
        yield {"metadata": {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}, "metrics": {"latencyMs": 1}}}
