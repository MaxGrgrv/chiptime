"""Athlete-supplied thresholds — the only door for zone/threshold context.

ADR-0008 §4: thresholds come from the user or the file, never from
inference. Everything is optional; analyses that need an absent threshold
are omitted with a note rather than estimated.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AthleteSettings:
    """All fields optional; absent means "don't compute what needs it"."""

    ftp_w: float | None = None  # cycling functional threshold power
    threshold_pace_s_per_km: float | None = None
    css_s_per_100m: float | None = None  # critical swim speed as pace/100m
    max_hr: float | None = None
    resting_hr: float | None = None
    lthr: float | None = None  # lactate-threshold HR
    hr_zone_bounds: tuple[float, ...] | None = None  # ascending upper bounds
    power_zone_bounds: tuple[float, ...] | None = None  # ascending upper bounds
    sex: str | None = None  # "male" | "female" — TRIMP coefficient
