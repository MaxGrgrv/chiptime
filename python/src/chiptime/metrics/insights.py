"""Single-workout report + machine-readable insights.

Insights follow the error-code philosophy (contract #5): a stable CODE for
agents, a human sentence, and numeric evidence. An insight only appears
when the data actually shows it; raw numbers live on the report itself.
Analyses that need absent inputs land in `omissions` with a reason —
a missing number beats an invented one (ADR-0008 §4/§5).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from chiptime.message import Message
from chiptime.metrics._basics import mean_max, swolf, time_in_zones
from chiptime.metrics.intervals import IntervalStructure, detect_structure
from chiptime.metrics.load import (
    TRIMP_MIN_COVERAGE,
    LoadEstimate,
    hr_coverage_fraction,
    weighted_avg_power,
    work_kj,
    workout_load,
)
from chiptime.metrics.pacing import Split, distance_splits, format_pace, session_pace_s
from chiptime.metrics.settings import AthleteSettings
from chiptime.metrics.sports import cadence_display, primary_signal, profile_for
from chiptime.metrics.zones import hr_zone_bounds, power_zone_bounds
from chiptime.model import Session

# --- insight thresholds (TS port copies verbatim) ------------------------
SPLIT_DELTA_PCT = 2.0  # first-vs-second-half speed delta to call a split
HR_DRIFT_PCT = 5.0  # efficiency drop that suggests aerobic fatigue
COASTING_SHARE_PCT = 25.0  # zero-power share worth remarking on (rides)
MIN_HALF_SAMPLES = 60  # halves need this many paired samples to compare
POWER_CURVE_WINDOWS = [5, 60, 300, 1200]

INSIGHT_CODES: dict[str, str] = {
    "PACING_NEGATIVE_SPLIT": "Second half faster than the first by more than 2%",
    "PACING_POSITIVE_SPLIT": "Second half slower than the first by more than 2%",
    "HR_DRIFT_HIGH": "Speed/power per heartbeat fell >5% first half to second (aerobic decoupling)",
    "COASTING_HIGH": "More than 25% of ride samples at 0 W",
    "WORKOUT_STRUCTURE": "Repeated interval structure found (label in evidence)",
}


@dataclass(frozen=True, slots=True)
class Insight:
    """One notable observation: a stable machine ``code`` (see
    `INSIGHT_CODES`), a human sentence, and the numbers behind it."""

    code: str
    message: str
    evidence: dict[str, Any]


@dataclass(slots=True)
class WorkoutReport:
    """Everything is optional and null-honest; `omissions` says what was not
    computed and why. `basis` strings mark where derived numbers came from."""

    sport: str
    sub_sport: str | None
    profile: str
    primary_signal: str  # power | speed | none
    duration_s: dict[str, float | None] = field(default_factory=dict)
    distance_m: float | None = None
    pace: dict[str, Any] | None = None  # {seconds, style, formatted, basis}
    avg_speed_kmh: float | None = None
    avg_speed_basis: str | None = None
    avg_primary: float | None = None
    max_primary: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    cadence: dict[str, Any] | None = None  # {value, units, note}
    weighted_avg_power: float | None = None
    variability_ratio: float | None = None  # weighted / avg power
    work_kj: float | None = None
    power_curve: dict[int, float | None] | None = None
    swolf: float | None = None
    splits: list[Split] = field(default_factory=list)
    structure: IntervalStructure | None = None
    hr_zones: dict[str, Any] | None = None  # {bounds, seconds, basis}
    power_zones: dict[str, Any] | None = None
    load: LoadEstimate | None = None
    insights: list[Insight] = field(default_factory=list)
    omissions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _plain(self)  # type: ignore[no-any-return]


@dataclass(slots=True)
class ActivityReport:
    """The full-file report: one `WorkoutReport` per session, in order.
    ``to_dict()`` gives the JSON-ready form the CLI emits with ``--json``."""

    sessions: list[WorkoutReport]

    def to_dict(self) -> dict[str, Any]:
        return {"sessions": [s.to_dict() for s in self.sessions]}


def _plain(obj: Any) -> Any:
    """Dataclass -> JSON-ready plain data (deterministic key order comes from
    dataclass field order + sort at dump time)."""
    import dataclasses
    from datetime import date, datetime

    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _plain(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj


# --- half comparisons ----------------------------------------------------


def _halves(session: Session, stream_name: str) -> tuple[list[float], list[float]]:
    s = session.records.stream(stream_name)
    if s is None:
        return [], []
    vals = [float(v) for v in s.values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    mid = len(vals) // 2
    return vals[:mid], vals[mid:]


def _pacing_insight(session: Session, stream: str | None) -> Insight | None:
    if stream is None:
        return None
    first, second = _halves(session, stream)
    if len(first) < MIN_HALF_SAMPLES or len(second) < MIN_HALF_SAMPLES:
        return None
    a = sum(first) / len(first)
    b = sum(second) / len(second)
    if a <= 0:
        return None
    delta_pct = (b - a) / a * 100.0
    ev = {
        "first_half_avg": round(a, 3),
        "second_half_avg": round(b, 3),
        "delta_pct": round(delta_pct, 1),
        "stream": stream,
    }
    if delta_pct >= SPLIT_DELTA_PCT:
        return Insight(
            "PACING_NEGATIVE_SPLIT", f"Second half {delta_pct:.1f}% faster than the first.", ev
        )
    if delta_pct <= -SPLIT_DELTA_PCT:
        return Insight(
            "PACING_POSITIVE_SPLIT", f"Second half {abs(delta_pct):.1f}% slower than the first.", ev
        )
    return None


def _hr_drift_insight(session: Session, stream: str | None) -> Insight | None:
    if stream is None:
        return None
    eff = session.records.stream(stream)
    hr = session.records.stream("heart_rate")
    if eff is None or hr is None:
        return None
    pairs = [
        (float(e), float(h))
        for e, h in zip(eff.values, hr.values, strict=True)
        if isinstance(e, (int, float))
        and not isinstance(e, bool)
        and isinstance(h, (int, float))
        and not isinstance(h, bool)
        and h > 0
    ]
    mid = len(pairs) // 2
    if mid < MIN_HALF_SAMPLES:
        return None

    def ef(chunk: list[tuple[float, float]]) -> float:
        se = sum(e for e, _ in chunk)
        sh = sum(h for _, h in chunk)
        return se / sh if sh > 0 else 0.0

    ef1, ef2 = ef(pairs[:mid]), ef(pairs[mid:])
    if ef1 <= 0:
        return None
    drift_pct = (ef1 - ef2) / ef1 * 100.0
    if drift_pct <= HR_DRIFT_PCT:
        return None
    return Insight(
        "HR_DRIFT_HIGH",
        f"Output per heartbeat fell {drift_pct:.1f}% from first half to second — aerobic drift.",
        {
            "drift_pct": round(drift_pct, 1),
            "stream": stream,
            "first_half_ef": round(ef1, 4),
            "second_half_ef": round(ef2, 4),
        },
    )


def _coasting_insight(session: Session) -> Insight | None:
    if profile_for(session).key != "cycling":
        return None
    pw = session.records.stream("power")
    if pw is None:
        return None
    present = [
        float(v) for v in pw.values if isinstance(v, (int, float)) and not isinstance(v, bool)
    ]
    if len(present) < MIN_HALF_SAMPLES:
        return None
    zero_share = sum(1 for v in present if v == 0.0) / len(present) * 100.0
    if zero_share < COASTING_SHARE_PCT:
        return None
    return Insight(
        "COASTING_HIGH",
        f"{zero_share:.0f}% of samples at 0 W (coasting).",
        {"zero_share_pct": round(zero_share, 1)},
    )


# --- report builder ------------------------------------------------------


def analyze_session(
    session: Session, messages: list[Message] | None = None, settings: AthleteSettings | None = None
) -> WorkoutReport:
    profile = profile_for(session)
    kind, stream = primary_signal(session)
    rep = WorkoutReport(
        sport=session.sport, sub_sport=session.sub_sport, profile=profile.key, primary_signal=kind
    )

    der, dec = session.derived, session.declared
    rep.duration_s = {
        "elapsed": der.elapsed_time_s or (dec.elapsed_time_s if dec else None),
        "timer": der.timer_time_s or (dec.timer_time_s if dec else None),
        "moving": der.moving_time_s,
    }
    rep.distance_m = der.distance_m or (dec.distance_m if dec else None)

    # pace / speed presentation per profile
    got = session_pace_s(session, profile.pace_style) if profile.pace_style != "speed" else None
    if got is not None:
        pace_s, basis = got
        rep.pace = {
            "seconds": round(pace_s, 1),
            "style": profile.pace_style,
            "formatted": format_pace(pace_s, profile.pace_style, suffix=True),
            "basis": basis,
        }
    if rep.distance_m:
        for key in ("moving", "timer", "elapsed"):
            dur_for_speed = rep.duration_s.get(key)
            if dur_for_speed:
                rep.avg_speed_kmh = round(rep.distance_m / dur_for_speed * 3.6, 2)
                rep.avg_speed_basis = key
                break

    # primary + hr stats from streams (avg dicts as declared fallback)
    def _stream_stats(name: str) -> tuple[float | None, float | None]:
        s = session.records.stream(name)
        if s is None:
            return None, None
        vals = [
            float(v) for v in s.values if isinstance(v, (int, float)) and not isinstance(v, bool)
        ]
        if not vals:
            return None, None
        return sum(vals) / len(vals), max(vals)

    if stream is not None:
        rep.avg_primary, rep.max_primary = _stream_stats(stream)
    rep.avg_hr, rep.max_hr = _stream_stats("heart_rate")

    cad_avg = _stream_stats("cadence")[0]
    if cad_avg is not None:
        val, units, note = cadence_display(cad_avg, profile)
        rep.cadence = {
            "value": round(val, 1) if val is not None else None,
            "units": units,
            "note": note,
        }

    pw = session.records.stream("power")
    if pw is not None:
        rep.weighted_avg_power = weighted_avg_power(pw.values)
        if rep.weighted_avg_power is not None:
            rep.weighted_avg_power = round(rep.weighted_avg_power, 1)
        if rep.weighted_avg_power and rep.avg_primary and kind == "power":
            rep.variability_ratio = round(rep.weighted_avg_power / rep.avg_primary, 3)
        kj = work_kj(session.records.time, pw.values)
        rep.work_kj = round(kj, 1) if kj is not None else None
        curve = mean_max(pw.values, POWER_CURVE_WINDOWS)
        rep.power_curve = {w: (round(v, 1) if v is not None else None) for w, v in curve.items()}

    if profile.distance_from_lengths and session.lengths:
        rep.swolf = swolf(session)[1]

    rep.splits = (
        distance_splits(session, 1000.0, style=profile.pace_style)
        if profile.pace_style == "per_km"
        else []
    )
    rep.structure = detect_structure(session, messages, settings)

    # zones: only from settings or the file, never estimated (ADR-0008 §4)
    hb, hbasis = hr_zone_bounds(settings, messages)
    if hb is not None and session.records.stream("heart_rate") is not None:
        hr_stream = session.records.stream("heart_rate")
        assert hr_stream is not None
        rep.hr_zones = {
            "bounds": list(hb),
            "basis": hbasis,
            "seconds": time_in_zones(session.records.time, hr_stream.values, list(hb)),
        }
    elif session.records.stream("heart_rate") is not None:
        rep.omissions.append("hr_zones: no zone bounds in settings or file")
    pb, pbasis = power_zone_bounds(settings, messages)
    if pb is not None and pw is not None:
        rep.power_zones = {
            "bounds": list(pb),
            "basis": pbasis,
            "seconds": time_in_zones(session.records.time, pw.values, list(pb)),
        }
    elif pw is not None:
        rep.omissions.append("power_zones: no zone bounds in settings or file")

    rep.load = workout_load(session, settings)
    if rep.load is None:
        if pw is not None and (settings is None or not settings.ftp_w):
            rep.omissions.append("load: power present but no ftp_w in settings")
        elif session.records.stream("heart_rate") is not None:
            if settings is None or not (settings.max_hr and settings.resting_hr):
                rep.omissions.append("load: hr present but no max_hr+resting_hr in settings")
            else:
                cov = hr_coverage_fraction(session)
                if cov is not None and cov < TRIMP_MIN_COVERAGE:
                    rep.omissions.append(
                        f"load: hr covers only {cov:.0%} of the session "
                        f"(< {TRIMP_MIN_COVERAGE:.0%}); trimp would understate load"
                    )

    for maybe in (
        _pacing_insight(session, stream),
        _hr_drift_insight(session, stream),
        _coasting_insight(session),
    ):
        if maybe is not None:
            rep.insights.append(maybe)
    if rep.structure is not None and rep.structure.repeats:
        rep.insights.append(
            Insight(
                "WORKOUT_STRUCTURE",
                "Interval structure: " + "; ".join(g.label for g in rep.structure.repeats),
                {"basis": rep.structure.basis, "labels": [g.label for g in rep.structure.repeats]},
            )
        )
    return rep


def analyze(result: Any, settings: AthleteSettings | None = None) -> ActivityReport:
    """Report per session from a ParseResult (uses .activity and .messages)."""
    activity = result.activity
    messages = result.messages
    if activity is None:
        return ActivityReport(sessions=[])
    return ActivityReport(
        sessions=[analyze_session(s, messages, settings) for s in activity.sessions]
    )
