"""Sport profiles — the table that knows how each sport measures itself.

Profiles are data, not subclasses (ADR-0008 §2): analytics code branches on
profile fields, never on sport names scattered through logic. Mapping per
docs/research/sport-metrics-domain.md §0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from chiptime.model import Session

PaceStyle = Literal["per_km", "per_100m", "per_500m", "speed"]

# Below this, a running cadence is per-leg strides/min on many devices
# (taxonomy #66); display convention is steps/min, so we double and label.
RUN_PER_LEG_CADENCE_MAX = 130.0


@dataclass(frozen=True, slots=True)
class SportProfile:
    """How one sport measures itself — profiles are data, not subclasses.

    Analytics code branches on these fields, never on sport names, so adding
    a sport is a table row, not a code path.

    Attributes:
        key: Profile name (``"running"``, ``"pool_swim"``, ...).
        pace_style: How speed is presented — ``per_km``, ``per_100m``,
            ``per_500m``, or ``speed`` (km/h).
        primary: Preferred intensity signal when its stream exists
            (``"power"`` or ``"speed"``).
        cadence_units: Display convention (``rpm``, ``spm``, strokes/min).
        cadence_double_if_per_leg: Running heuristic — cadence below 130 is
            per-leg strides on many devices; doubled for display, labeled.
        distance_from_lengths: Pool truth — distance is lengths x pool size,
            never GPS.
    """

    key: str
    pace_style: PaceStyle
    primary: Literal["power", "speed"]  # preferred intensity signal when present
    cadence_units: str  # display convention: rpm | spm | strokes/min
    cadence_double_if_per_leg: bool = False
    distance_from_lengths: bool = False  # pool truth: lengths x pool size, never GPS


RUNNING = SportProfile("running", "per_km", "speed", "spm", cadence_double_if_per_leg=True)
CYCLING = SportProfile("cycling", "speed", "power", "rpm")
POOL_SWIM = SportProfile(
    "pool_swim", "per_100m", "speed", "strokes/min", distance_from_lengths=True
)
OPEN_WATER_SWIM = SportProfile("open_water_swim", "per_100m", "speed", "strokes/min")
ROWING = SportProfile("rowing", "per_500m", "power", "strokes/min")
HIKING = SportProfile("hiking", "per_km", "speed", "spm")
XC_SKIING = SportProfile("cross_country_skiing", "per_km", "speed", "spm")
GENERIC = SportProfile("generic", "per_km", "speed", "rpm")

_BY_SPORT: dict[str, SportProfile] = {
    "running": RUNNING,
    "cycling": CYCLING,
    "rowing": ROWING,
    "hiking": HIKING,
    "walking": HIKING,
    "cross_country_skiing": XC_SKIING,
}


def profile_for(session: Session) -> SportProfile:
    """Resolve (sport, sub_sport) → profile; unknown sports get GENERIC
    (correct-but-shallow beats wrong-but-specific)."""
    sport = (session.sport or "").lower()
    sub = (session.sub_sport or "").lower()
    if sport == "swimming":
        return OPEN_WATER_SWIM if sub == "open_water" else POOL_SWIM
    if sub == "indoor_rowing" or (sport == "fitness_equipment" and "row" in sub):
        return ROWING
    return _BY_SPORT.get(sport, GENERIC)


def primary_signal(session: Session) -> tuple[str, str | None]:
    """The intensity signal actually available: profile preference constrained
    by which streams exist. Returns (kind, stream_name); kind is
    "power" | "speed" | "none"."""
    p = profile_for(session)
    if p.primary == "power":
        s = session.records.stream("power")
        if s is not None and s.present_count > 0:
            return "power", "power"
    for name in ("enhanced_speed", "speed"):
        s = session.records.stream(name)
        if s is not None and s.present_count > 0:
            return "speed", name
    return "none", None


def cadence_display(
    avg_cadence: float | None,
    profile: SportProfile,
) -> tuple[float | None, str, str | None]:
    """(value, units, note). The doubling heuristic is labeled, never silent."""
    if avg_cadence is None:
        return None, profile.cadence_units, None
    if profile.cadence_double_if_per_leg and avg_cadence < RUN_PER_LEG_CADENCE_MAX:
        return avg_cadence * 2.0, profile.cadence_units, "doubled_per_leg_cadence"
    return avg_cadence, profile.cadence_units, None
