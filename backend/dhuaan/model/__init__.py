"""Dhuaan smoke model ("HYSPLIT-lite" Lagrangian particles). Pure numpy.

    from dhuaan.model import run, Fire, MetField, Receptor
    arts = run(fires, met, receptors, population_grid, t0, members=5, seed=0,
               afternoon_mode="none", district_of=lookup)
    summary = arts.pop("_summary")      # goes into meta.json; not written as a file
"""
from .core import ModelResult, run, simulate
from .params import Member, Params
from .types import Fire, MetField, Receptor

MODEL_VERSION = "hysplit-lite-0.1"

__all__ = ["run", "simulate", "ModelResult", "Fire", "MetField", "Receptor", "Params", "Member", "MODEL_VERSION"]
