"""Shared fixtures: a LocalStore over tests/agent/fixtures (copied to tmp so cache writes stay out of the repo),
and a fixed clock. ScriptedModel (scripted_model.py) stands in for the LLM."""
from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dhuaan.agent import data, timeutil, tools
from dhuaan.store import LocalStore

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 10, 8, 3, 0, tzinfo=timezone.utc)  # 08:30 IST, 3 h after the fixture run t0


@pytest.fixture
def store(tmp_path, monkeypatch):
    shutil.copytree(FIXTURES, tmp_path, dirs_exist_ok=True)
    st = LocalStore(tmp_path)
    data.use_store(st)
    monkeypatch.setattr(timeutil, "now_utc", lambda: NOW)
    tools._obs_cache.clear()
    monkeypatch.setattr(tools, "observed_near", lambda lat, lon: None)
    yield st
    data.use_store(None)
