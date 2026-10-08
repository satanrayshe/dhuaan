"""Stage the Lambda code: backend/dhuaan + backend/data -> infra/.stage/app (cleaned every run).

Every function's CodeUri points at infra/.stage/app, so tests/, out/, cache/, .venv and
__pycache__ never ship. Third-party deps come from the layers (see build_layers.py).

    python infra/stage.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

INFRA = Path(__file__).resolve().parent
BACKEND = INFRA.parent / "backend"
STAGE = INFRA / ".stage" / "app"
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache", ".DS_Store", "*.egg-info")


def _rmtree(p: Path) -> None:
    def onerror(func, path, _exc):  # read-only files on Windows
        import os, stat
        os.chmod(path, stat.S_IWRITE)
        func(path)
    if p.exists():
        shutil.rmtree(p, onerror=onerror)


def dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())


def stage() -> Path:
    src_pkg = BACKEND / "dhuaan"
    if not (src_pkg / "__init__.py").exists():
        sys.exit(f"stage: {src_pkg} is not a package")
    _rmtree(STAGE)
    STAGE.mkdir(parents=True)
    shutil.copytree(src_pkg, STAGE / "dhuaan", ignore=IGNORE)
    data = BACKEND / "data"
    if data.exists():
        shutil.copytree(data, STAGE / "data", ignore=IGNORE)
    else:
        (STAGE / "data").mkdir()
    n = sum(1 for f in STAGE.rglob("*") if f.is_file())
    print(f"stage: {n} files, {dir_size(STAGE) / 1e6:.2f} MB -> {STAGE}")
    return STAGE


if __name__ == "__main__":
    stage()
