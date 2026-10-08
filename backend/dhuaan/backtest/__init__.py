"""Phase 2: backtest (A vs B on the 11 Nov 2025 episode), calibration, afternoon ratio, static-hotspot mask.

Entry points:
    uv run python -m dhuaan.backtest.hotspots   # backend/data/static_hotspots.json (FIRMS VIIRS Jan-Aug 2025)
    uv run python -m dhuaan.backtest.ratio      # backend/data/afternoon_ratio.json + facts.json (GK2A 2025)
    uv run python -m dhuaan.backtest.run        # backend/out/latest/backtest.json
"""
