"""ask(): one grounded Q&A turn with the Strands agent (the /api/ask contract).

Flow: cache lookup -> Strands Agent with read-only tools (tool calls captured by an AfterToolCallEvent hook)
-> grounding check -> if any number is unverified, one corrective follow-up in the same conversation
-> cache the result under cache/answers/<hash>.json in the artifact store.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import unicodedata
from typing import Any, Callable

from strands import Agent, ModelRetryStrategy
from strands.hooks import AfterModelCallEvent, AfterToolCallEvent, BeforeModelCallEvent
from strands.types.exceptions import EventLoopException

from dhuaan.agent import data, grounding, models, prompts, tools

log = logging.getLogger(__name__)
LANGS = ("en", "hi", "pa")
MAX_QUESTION = 500


class LLMBudgetExceeded(RuntimeError):
    pass


class _Budget:
    """Process-wide cap on successful model calls (env DHUAAN_MAX_LLM_CALLS; 0/unset = unlimited).

    Only calls that returned (no exception) count: 404/429/503 responses don't use generation quota."""

    def __init__(self) -> None:
        self.calls = 0
        self.failed = 0
        self._lock = threading.Lock()

    def check(self) -> None:
        cap = int(os.environ.get("DHUAAN_MAX_LLM_CALLS", "0") or 0)
        with self._lock:
            if cap and self.calls >= cap:
                raise LLMBudgetExceeded(f"LLM call budget of {cap} reached")

    def record(self, ok: bool) -> None:
        with self._lock:
            if ok:
                self.calls += 1
            else:
                self.failed += 1


BUDGET = _Budget()


class TraceRecorder:
    """Collects every tool call (name, args, parsed result) and counts model calls for one ask()."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.model_calls = 0

    def on_tool(self, event: AfterToolCallEvent) -> None:
        tu = event.tool_use
        res: Any = None
        content = (event.result or {}).get("content") or []
        for c in content:
            if "json" in c:
                res = c["json"]
            elif "text" in c:
                try:
                    res = json.loads(c["text"])
                except ValueError:
                    res = c["text"]
        self.calls.append({"tool": tu.get("name"), "args": tu.get("input") or {}, "result": res})

    def on_model(self, event: BeforeModelCallEvent) -> None:
        BUDGET.check()

    def after_model(self, event: AfterModelCallEvent) -> None:
        ok = event.exception is None
        BUDGET.record(ok)
        self.model_calls += 1 if ok else 0

    def attach(self, agent: Agent) -> None:
        agent.hooks.add_callback(AfterToolCallEvent, self.on_tool)
        agent.hooks.add_callback(BeforeModelCallEvent, self.on_model)
        agent.hooks.add_callback(AfterModelCallEvent, self.after_model)

    def facts(self) -> list[Any]:
        return [c["result"] for c in self.calls] + [c["args"] for c in self.calls] + [prompts.STATIC_FACTS]

    def trace(self) -> list[dict]:
        return [{"tool": c["tool"], "args": c["args"], "summary": tools.summarize(c["tool"], c["result"])} for c in self.calls]


def _root_cause(e: BaseException) -> BaseException:
    """Strands wraps hook/model errors in EventLoopException; find the original."""
    seen = 0
    while isinstance(e, EventLoopException) and e.__cause__ is not None and seen < 5:
        e, seen = e.__cause__, seen + 1
    return e


def _call(agent: Agent, prompt: str) -> str:
    try:
        return str(agent(prompt)).strip()
    except EventLoopException as e:
        raise _root_cause(e) from e


def normalise_question(q: str) -> str:
    q = unicodedata.normalize("NFC", q or "").casefold()
    q = re.sub(r"[\s ]+", " ", q).strip()
    return q.rstrip("?.!।؟ ")


def cache_key(question: str, place_id: str | None, lang: str) -> str:
    raw = json.dumps([data.run_id(), normalise_question(question), place_id or "", lang], ensure_ascii=False)
    return "cache/answers/" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32] + ".json"


ModelFactory = Callable[[str | None], Any]  # model_id override -> Strands model


def _build_agent(model: Any, lang: str, place_id: str | None, rec: TraceRecorder) -> Agent:
    agent = Agent(model=model, tools=list(tools.ALL_TOOLS), system_prompt=prompts.system_prompt(lang, place_id),
                  callback_handler=None, retry_strategy=ModelRetryStrategy(max_attempts=2, initial_delay=2, max_delay=8))
    rec.attach(agent)
    return agent


def _user_prompt(question: str, place_id: str | None, lang: str) -> str:
    hint = f"[selected place_id: {place_id}] " if place_id else ""
    return f"{hint}[answer language: {prompts.LANG_NAMES[lang]}]\n{question.strip()}"


def _run(question: str, place_id: str | None, lang: str, model_factory: ModelFactory, model_id: str | None) -> dict:
    rec = TraceRecorder()
    agent = _build_agent(model_factory(model_id), lang, place_id, rec)
    answer = _call(agent, _user_prompt(question, place_id, lang))
    g = grounding.check(answer, rec.facts(), question)
    retried = False
    if g["unverified"]:
        retried = True
        try:
            fixed = _call(agent, prompts.correction(g["unverified"]))
            g2 = grounding.check(fixed, rec.facts(), question)
            if fixed and len(g2["unverified"]) <= len(g["unverified"]):
                answer, g = fixed, g2
        except Exception as e:  # budget, quota or overload during the retry: keep the first answer (UI shows the warning)
            log.warning("grounding retry failed (%s); keeping first answer", type(e).__name__)
    return {"answer": answer, "grounding": g, "trace": rec.trace(), "retried": retried, "model_calls": rec.model_calls}


def ask(question: str, place_id: str | None = None, lang: str = "en", *,
        model_factory: ModelFactory | None = None, use_cache: bool = True) -> dict:
    """Answer one question. Returns {answer, lang, tool_trace, grounding, model, cached} (+ retried, model_calls)."""
    if lang not in LANGS:
        raise ValueError(f"lang must be one of {LANGS}")
    question = (question or "").strip()
    if not question or len(question) > MAX_QUESTION:
        raise ValueError(f"question must be 1-{MAX_QUESTION} characters")
    st = data.store()
    key = cache_key(question, place_id, lang)
    if use_cache:
        hit = st.get_json(key)
        if hit:
            return {**hit, "cached": True}
    factory = model_factory or (lambda mid: models.build_model(model_id=mid))
    out, model_id, last_err = None, None, None
    for model_id in models.candidates():
        try:
            out = _run(question, place_id, lang, factory, model_id)
            break
        except LLMBudgetExceeded:
            raise
        except Exception as e:
            kind = models.classify_error(e)
            if kind is None:
                raise
            if kind == "unavailable":
                models.mark_unavailable(model_id)
            log.warning("model %s %s; trying the next one", model_id, kind)
            last_err = e
    if out is None:
        raise last_err or RuntimeError("no model available")
    result = {"answer": out["answer"], "lang": lang, "tool_trace": out["trace"], "grounding": out["grounding"],
              "model": models.model_label(model_id=model_id), "cached": False,
              "retried": out["retried"], "model_calls": out["model_calls"]}
    if use_cache and out["answer"]:
        try:
            st.put_json(key, {k: v for k, v in result.items() if k != "cached"})
        except Exception as e:  # read-only store or S3 permission problem must not break the answer
            log.warning("answer cache write failed: %s", type(e).__name__)
    return result
