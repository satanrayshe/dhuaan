"""Build the two Lambda layers for python3.12 / x86_64 (manylinux wheels only, so it works on Windows).

    DepsLayer  -> infra/layers/build/deps/python   numpy, h5py, requests, python-dotenv
    AgentLayer -> infra/layers/build/agent/python  strands-agents[gemini] + deps, minus anything the
                                                   runtime (boto3/botocore) or DepsLayer already has

Versions are pinned to backend/uv.lock (via `uv export`) so Lambda runs what the tests ran.
Uses `uv pip install --target --python-platform x86_64-manylinux_2_34` (markers evaluated for Linux),
falling back to `pip install --platform manylinux2014_x86_64 --platform manylinux_2_28_x86_64
--platform manylinux_2_34_x86_64 --only-binary=:all: --python-version 3.12 --implementation cp`.
manylinux_2_34 is right for the python3.12 runtime (Amazon Linux 2023, glibc 2.34); numpy 2.5 ships
no manylinux2014 wheels any more, so manylinux2014 alone cannot resolve.

    python infra/build_layers.py            # build if missing
    python infra/build_layers.py --force    # rebuild
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

INFRA = Path(__file__).resolve().parent
BACKEND = INFRA.parent / "backend"
BUILD = INFRA / "layers" / "build"

LAYERS: dict[str, list[str]] = {
    "deps": ["numpy", "h5py", "requests", "python-dotenv"],
    "agent": ["strands-agents[gemini]"],
}
# Provided by the Lambda python3.12 runtime: never ship them.
RUNTIME_PROVIDED = {"boto3", "botocore", "s3transfer", "jmespath"}
# Lambda limit: function code + all its layers <= 250 MB unzipped. ApiFn/AdviseFn attach both layers.
LIMIT_MB = 250.0
CODE_HEADROOM_MB = 20.0  # leave room for the function package (dhuaan + data)

# Files/dirs that are never needed at runtime.
# (`testing` dirs are kept: numpy.testing is imported by some libraries at runtime.)
PRUNE_DIRS = {"__pycache__", "tests", "test", "benchmarks"}
PRUNE_SUFFIXES = (".pyc", ".pyo", ".pyi", ".c", ".cpp", ".h", ".pxd", ".pyx")


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def constraints_file(tmp: Path) -> Path:
    """Pin every package to the version in backend/uv.lock."""
    out = tmp / "constraints.txt"
    res = subprocess.run(
        ["uv", "export", "--frozen", "--no-dev", "--no-hashes", "--no-emit-project", "--format", "requirements-txt"],
        cwd=BACKEND, capture_output=True, text=True,
    )
    if res.returncode != 0:
        print("build_layers: uv export failed, building unpinned:\n" + res.stderr, file=sys.stderr)
        out.write_text("")
        return out
    pins = []
    for line in res.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        spec = line.split(";")[0].strip()  # markers are re-evaluated by the installer for the target
        m = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?==(\S+)$", spec)
        if m:
            pins.append(f"{m.group(1)}=={m.group(3)}")
    out.write_text("\n".join(pins) + "\n")
    return out


def install(pkgs: list[str], target: Path, constraints: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    if shutil.which("uv"):
        cmd = ["uv", "pip", "install", "--target", str(target), "--python-platform", "x86_64-manylinux_2_34",
               "--python-version", "3.12", "--only-binary", ":all:", "-c", str(constraints), "--quiet", *pkgs]
    else:
        cmd = [sys.executable, "-m", "pip", "install", "--platform", "manylinux2014_x86_64",
               "--platform", "manylinux_2_28_x86_64", "--platform", "manylinux_2_34_x86_64", "--only-binary=:all:",
               "--python-version", "3.12", "--implementation", "cp", "-t", str(target), "-c", str(constraints),
               "--upgrade", "--quiet", *pkgs]
    print("build_layers: " + " ".join(cmd[:3]) + " ... " + " ".join(pkgs))
    subprocess.run(cmd, check=True)


def dist_map(site: Path) -> dict[str, tuple[Path, list[Path]]]:
    """normalized dist name -> (dist-info dir, top-level paths it installed), from RECORD."""
    out: dict[str, tuple[Path, list[Path]]] = {}
    for di in site.glob("*.dist-info"):
        name = norm(di.name[: -len(".dist-info")].rsplit("-", 1)[0])
        tops: set[Path] = set()
        record = di / "RECORD"
        if record.exists():
            for row in record.read_text(encoding="utf-8").splitlines():
                rel = row.split(",")[0]
                if not rel or rel.startswith(".."):
                    continue
                first = rel.split("/")[0]
                tops.add(site / first)
        tops.add(di)
        out[name] = (di, sorted(tops))
    return out


def remove_dists(site: Path, names: set[str]) -> list[str]:
    removed = []
    dm = dist_map(site)
    # Never delete a top-level dir that a kept dist also installed into (namespace packages like google/).
    keep_tops = {t for n, (_, tops) in dm.items() if n not in names for t in tops}
    for n, (_, tops) in dm.items():
        if n in names:
            for t in tops:
                if t in keep_tops and t.is_dir() and not t.name.endswith(".dist-info"):
                    continue
                if t.is_dir():
                    shutil.rmtree(t, ignore_errors=True)
                elif t.exists():
                    t.unlink()
            removed.append(n)
    return sorted(removed)


def slim(site: Path) -> None:
    for p in sorted(site.rglob("*"), key=lambda x: len(x.parts), reverse=True):
        if p.is_dir() and p.name in PRUNE_DIRS:
            shutil.rmtree(p, ignore_errors=True)
        elif p.is_file() and p.suffix in PRUNE_SUFFIXES:
            p.unlink(missing_ok=True)
    shutil.rmtree(site / "bin", ignore_errors=True)  # console scripts are useless in Lambda


def size_mb(p: Path) -> float:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1e6


def build(name: str, constraints: Path, exclude: set[str]) -> Path:
    root = BUILD / name
    site = root / "python"
    if root.exists():
        shutil.rmtree(root)
    install(LAYERS[name], site, constraints)
    removed = remove_dists(site, exclude)
    if removed:
        print(f"build_layers: [{name}] removed (provided elsewhere): {', '.join(removed)}")
    slim(site)
    return root


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="rebuild even if the layers exist")
    args = ap.parse_args()

    ready = all((BUILD / n / "python").is_dir() and any((BUILD / n / "python").iterdir()) for n in LAYERS)
    if ready and not args.force:
        print("build_layers: layers already built (use --force to rebuild)")
    else:
        BUILD.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            cons = constraints_file(Path(tmp))
            deps = build("deps", cons, RUNTIME_PROVIDED)
            deps_dists = set(dist_map(deps / "python"))
            build("agent", cons, RUNTIME_PROVIDED | deps_dists)

    sizes = {n: size_mb(BUILD / n) for n in LAYERS}
    for n, s in sizes.items():
        print(f"build_layers: {n:6s} layer {s:7.1f} MB unzipped  ({BUILD / n})")
    combined = sizes["deps"] + sizes["agent"]
    budget = LIMIT_MB - CODE_HEADROOM_MB
    print(f"build_layers: deps+agent {combined:.1f} MB (budget {budget:.0f} MB = 250 MB limit - {CODE_HEADROOM_MB:.0f} MB code headroom)")
    if combined > budget:
        sys.exit("build_layers: FAIL - layers too large for one function")
    print("build_layers: OK")


if __name__ == "__main__":
    main()
