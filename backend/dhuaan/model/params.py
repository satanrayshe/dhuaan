"""Model parameters. Defaults follow docs/CONTRACTS.md and prep/01-project-spec.md."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Member:
    """One ensemble member's perturbation."""
    speed: float = 1.0        # wind speed multiplier
    turn_deg: float = 0.0     # wind direction rotation (deg, counter-clockwise)
    kh: float = 1.0           # K_h multiplier


DEFAULT_MEMBERS = (
    Member(1.0, 0.0, 1.0),       # member 0: unperturbed
    Member(0.85, 15.0, 0.5),
    Member(1.15, -15.0, 2.0),
    Member(0.85, -15.0, 2.0),
    Member(1.15, 15.0, 0.5),
)


def members_for(n: int) -> tuple[Member, ...]:
    """First n members; beyond 5, cycle the perturbation corners."""
    if n <= len(DEFAULT_MEMBERS):
        return DEFAULT_MEMBERS[:n]
    return DEFAULT_MEMBERS + tuple(DEFAULT_MEMBERS[1 + (i % 4)] for i in range(n - len(DEFAULT_MEMBERS)))


@dataclass(frozen=True)
class Params:
    # sources
    eps_km: float = 1.5
    window_h: float = 6.0
    lookback_h: float = 48.0          # fires older than t0-48h are not modelled
    burn_before_h: float = 0.5        # burn window = [first_det - 0.5 h, last_det + 1.5 h]
    burn_after_h: float = 1.5
    ce_kg_per_mj: float = 0.02        # PM2.5 emission per MJ of fire energy (FRE coefficient)
    burn_duration_s: float = 7200.0   # energy per detection = FRP x 2 h
    frp_default_mw: float = 10.0
    afternoon_start_ist: float = 16.0
    afternoon_end_ist: float = 19.0
    afternoon_ratio_default: float = 2.0
    min_particles: int = 20
    max_particles: int = 400
    particle_cap: int = 50_000        # per member
    release_jitter_m: float = 300.0
    # transport
    dt_s: float = 900.0
    tau_h: float = 48.0               # exponential removal; float("inf") disables
    kh_night: float = 1.0e3
    kh_day: float = 5.0e3
    blh_lo: float = 300.0
    blh_hi: float = 1500.0
    kh_scale: float = 1.0             # global K_h multiplier (0 = no diffusion; used in tests)
    z925_m: float = 750.0
    z850_m: float = 1500.0
    # concentration / exposure
    h_km: float = 10.0
    blh_floor_m: float = 50.0
    school_factor: float = 1.5
    school_hours_ist: tuple[int, int] = (7, 14)   # [07:00, 14:00)
    exposure_hours: int = 48
    # artifacts
    trip_step_min: int = 30
    max_trips: int = 6000
    arrival_frac: float = 0.15
    scale_pct: float = 99.0
    members: tuple[Member, ...] = field(default=DEFAULT_MEMBERS)
