"""Pace math done right: internal SI (m/s, s), pace strictly as presentation.

The inverse-metric trap (research doc §0): pace is 1/speed, so paces are
never averaged — aggregate distance/time first, convert last. Pace at
standstill is undefined and returns None, never a huge number.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from chiptime.metrics.sports import PaceStyle
from chiptime.model import Session

_METERS: dict[str, float] = {"per_km": 1000.0, "per_100m": 100.0, "per_500m": 500.0}
PACE_SUFFIX: dict[str, str] = {"per_km": "/km", "per_100m": "/100m", "per_500m": "/500m"}

# Concept2's published erg relation: W = 2.80 / pace^3, pace in seconds/meter.
CONCEPT2_COEFF = 2.80


def pace_seconds(speed_mps: float | None, style: PaceStyle) -> float | None:
    """Seconds per style unit; None for absent/zero speed or style "speed"."""
    if style == "speed" or speed_mps is None or speed_mps <= 0.0:
        return None
    return _METERS[style] / speed_mps


def speed_from_pace(pace_s: float, style: PaceStyle) -> float:
    if style == "speed" or pace_s <= 0.0:
        raise ValueError(f"no distance base for style {style!r} / pace {pace_s!r}")
    return _METERS[style] / pace_s


def format_pace(pace_s: float | None, style: PaceStyle, *, suffix: bool = False) -> str | None:
    """ "4:20" (/km, /100m) or "1:52.5" (/500m, rowing shows tenths).

    Rounding is explicit half-up (int(x + 0.5)) so Python's banker's rounding
    can never make two runtimes disagree on a boundary value.
    """
    if pace_s is None:
        return None
    if style == "speed":
        raise ValueError("style 'speed' has no pace representation; use format_speed_kmh")
    if style == "per_500m":
        tenths = int(pace_s * 10 + 0.5)
        minutes, rem = divmod(tenths, 600)
        secs, tenth = divmod(rem, 10)
        out = f"{minutes}:{secs:02d}.{tenth}"
    else:
        total = int(pace_s + 0.5)
        minutes, secs = divmod(total, 60)
        out = f"{minutes}:{secs:02d}"
    return out + PACE_SUFFIX[style] if suffix else out


def format_speed_kmh(speed_mps: float | None, *, suffix: bool = False) -> str | None:
    if speed_mps is None:
        return None
    out = f"{speed_mps * 3.6:.1f}"
    return out + " km/h" if suffix else out


def split_500m_to_watts(split_s: float) -> float:
    """Concept2 published relation (see CONCEPT2_COEFF)."""
    pace_s_per_m = split_s / 500.0
    return CONCEPT2_COEFF / (pace_s_per_m * pace_s_per_m * pace_s_per_m)


def watts_to_split_500m(watts: float) -> float:
    return 500.0 * float((CONCEPT2_COEFF / watts) ** (1.0 / 3.0))


@dataclass(frozen=True, slots=True)
class Split:
    """One distance split. Absent streams give None fields, never zeros."""

    index: int  # 1-based
    start_m: float
    end_m: float
    duration_s: float  # elapsed between boundary crossings (stops included;
    # stopped time is visible separately via session gaps)
    avg_speed_mps: float | None
    pace_s: float | None  # per requested style; None where undefined
    avg_hr: float | None
    avg_power: float | None
    ascent_m: float | None
    descent_m: float | None
    partial: bool = False


def distance_splits(
    session: Session, split_m: float = 1000.0, *, style: PaceStyle = "per_km"
) -> list[Split]:
    """Distance-domain splits from the cumulative distance stream.

    Boundary crossings are linearly interpolated between records; each
    record's samples are attributed to the split where its step started
    (deterministic). No distance stream → [] (pool swims split by lengths
    instead — F24). HR/power averages are record-domain means (1 Hz files:
    time-domain too); altitude ascent/descent from consecutive present values.
    """
    rec = session.records
    dist = rec.stream("distance")
    if dist is None or rec.n == 0 or split_m <= 0:
        return []
    hr_s = rec.stream("heart_rate")
    pw_s = rec.stream("power")
    alt_stream = rec.stream("enhanced_altitude") or rec.stream("altitude")

    pts: list[tuple[float, float, int]] = []  # (t_rel_s, distance_m, record_idx)
    t0: datetime | None = None
    for i, t in enumerate(rec.time):
        d = dist.values[i]
        if t is None or not isinstance(d, (int, float)) or isinstance(d, bool):
            continue
        if t0 is None:
            t0 = t
        pts.append(((t - t0).total_seconds(), float(d), i))
    if len(pts) < 2:
        return []

    splits: list[Split] = []
    hr_sum = 0.0
    hr_n = 0
    pw_sum = 0.0
    pw_n = 0
    asc = 0.0
    desc = 0.0
    alt_seen = False
    prev_alt: float | None = None

    def _sample(idx: int) -> None:
        nonlocal hr_sum, hr_n, pw_sum, pw_n, asc, desc, alt_seen, prev_alt
        if hr_s is not None:
            v = hr_s.values[idx]
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                hr_sum += float(v)
                hr_n += 1
        if pw_s is not None:
            v = pw_s.values[idx]
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                pw_sum += float(v)
                pw_n += 1
        if alt_stream is not None:
            v = alt_stream.values[idx]
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                fv = float(v)
                if prev_alt is not None:
                    delta = fv - prev_alt
                    if delta > 0:
                        asc += delta
                    else:
                        desc += -delta
                prev_alt = fv
                alt_seen = True

    def _emit(start_t: float, end_t: float, start_d: float, end_d: float, partial: bool) -> None:
        nonlocal hr_sum, hr_n, pw_sum, pw_n, asc, desc, alt_seen
        dur = end_t - start_t
        covered = end_d - start_d
        speed = covered / dur if dur > 0 else None
        splits.append(
            Split(
                index=len(splits) + 1,
                start_m=start_d,
                end_m=end_d,
                duration_s=dur,
                avg_speed_mps=speed,
                pace_s=pace_seconds(speed, style),
                avg_hr=hr_sum / hr_n if hr_n else None,
                avg_power=pw_sum / pw_n if pw_n else None,
                ascent_m=asc if alt_seen else None,
                descent_m=desc if alt_seen else None,
                partial=partial,
            )
        )
        hr_sum = pw_sum = asc = desc = 0.0
        hr_n = pw_n = 0
        alt_seen = False

    start_t, start_d, first_idx = pts[0]
    boundary = start_d + split_m
    _sample(first_idx)
    prev_t, prev_d = start_t, start_d
    for cur_t, cur_d, cur_i in pts[1:]:
        while cur_d >= boundary and cur_d > prev_d:
            frac = (boundary - prev_d) / (cur_d - prev_d)
            t_cross = prev_t + frac * (cur_t - prev_t)
            _emit(start_t, t_cross, start_d, boundary, partial=False)
            start_t, start_d = t_cross, boundary
            boundary += split_m
        _sample(cur_i)
        prev_t, prev_d = cur_t, cur_d
    if prev_d - start_d > 0.5:  # trailing partial beyond half a meter
        _emit(start_t, prev_t, start_d, prev_d, partial=True)
    return splits


def session_pace_s(session: Session, style: PaceStyle) -> tuple[float, str] | None:
    """Overall pace from totals, preferring the moving denominator
    (research §0), falling back timer → elapsed. Returns (pace_s, basis)."""
    dist = None
    for t in (session.derived, session.declared):
        if t is not None and t.distance_m is not None and t.distance_m > 0:
            dist = t.distance_m
            break
    if dist is None:
        return None
    for attr, basis in (
        ("moving_time_s", "moving"),
        ("timer_time_s", "timer"),
        ("elapsed_time_s", "elapsed"),
    ):
        for t in (session.derived, session.declared):
            if t is None:
                continue
            dur = getattr(t, attr)
            if dur is not None and dur > 0:
                pace = pace_seconds(dist / dur, style)
                if pace is not None:
                    return pace, basis
    return None
