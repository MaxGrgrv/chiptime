"""Training-load estimators — published math, neutral names, explicit basis.

Formulas (all public science; names are ours, math is cited):
- Weighted average power: 30-sample rolling mean -> mean of 4th powers ->
  4th root (the Coggan-style weighting, published in Training and Racing
  with a Power Meter; trademarked *names* avoided per ADR-0008 §7).
- load_score = hours x intensity_ratio^2 x 100 (classic stress formula).
- TRIMP (Banister 1991): sum dt_min x HRr x 0.64 x e^(k x HRr),
  HRr = (HR - rest)/(max - rest); k = 1.92 male / 1.67 female.
- fitness/fatigue: exponentially-weighted load with 42 d / 7 d time
  constants (Banister impulse-response; fitness/fatigue/form naming per
  intervals.icu / Strava convention). form(t) = fitness(t-1) - fatigue(t-1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from chiptime.metrics._basics import ZONE_DT_CAP_S
from chiptime.metrics.settings import AthleteSettings
from chiptime.model import Session

WEIGHTED_POWER_WINDOW = 30  # samples (record domain; ~30 s at 1 Hz)
TRIMP_COEFF = 0.64
TRIMP_K_MALE = 1.92  # used as documented default when sex unset
TRIMP_K_FEMALE = 1.67
TRIMP_MIN_COVERAGE = 0.5  # HR must cover >= this fraction of the session
FITNESS_TC_DAYS = 42.0
FATIGUE_TC_DAYS = 7.0


def _present(values: list[object]) -> list[float]:
    return [float(v) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]


def weighted_avg_power(values: list[object]) -> float | None:
    """4th-power-weighted mean over a 30-sample rolling mean. Zeros are real
    (coasting) and stay in; nulls (dropouts) are skipped, never zero-filled.
    None when fewer than one full window of samples is present."""
    vals = _present(values)
    n = len(vals)
    if n < WEIGHTED_POWER_WINDOW:
        return None
    acc = 0.0
    fourth_sum = 0.0
    window_means = n - WEIGHTED_POWER_WINDOW + 1
    for i in range(n):
        acc += vals[i]
        if i >= WEIGHTED_POWER_WINDOW:
            acc -= vals[i - WEIGHTED_POWER_WINDOW]
        if i >= WEIGHTED_POWER_WINDOW - 1:
            m = acc / WEIGHTED_POWER_WINDOW
            fourth_sum += m * m * m * m
    return float((fourth_sum / window_means) ** 0.25)


def work_kj(times: list[datetime | None], values: list[object]) -> float | None:
    """Mechanical work: sum W x dt / 1000, dt capped at the gap policy
    (a recording gap is a gap, not free kilojoules)."""
    total = 0.0
    seen = False
    for i in range(len(times) - 1):
        t0, t1 = times[i], times[i + 1]
        v = values[i]
        if t0 is None or t1 is None or not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        dt = (t1 - t0).total_seconds()
        if dt <= 0:
            continue
        total += float(v) * min(dt, ZONE_DT_CAP_S)
        seen = True
    return total / 1000.0 if seen else None


def intensity_ratio(weighted_power: float, ftp_w: float) -> float:
    return weighted_power / ftp_w


def load_score(duration_s: float, intensity: float) -> float:
    return duration_s / 3600.0 * intensity * intensity * 100.0


def trimp(
    times: list[datetime | None],
    hr_values: list[object],
    *,
    resting_hr: float,
    max_hr: float,
    sex: str | None = None,
) -> float | None:
    """Banister TRIMP. `sex` picks the published coefficient (1.92 male /
    1.67 female); unset uses the male coefficient — callers surface that in
    the basis string. None if the HR reserve is degenerate or no data."""
    if max_hr <= resting_hr:
        return None
    k = TRIMP_K_FEMALE if sex == "female" else TRIMP_K_MALE
    reserve = max_hr - resting_hr
    total = 0.0
    seen = False
    for i in range(len(times) - 1):
        t0, t1 = times[i], times[i + 1]
        v = hr_values[i]
        if t0 is None or t1 is None or not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        dt = (t1 - t0).total_seconds()
        if dt <= 0:
            continue
        hrr = (float(v) - resting_hr) / reserve
        hrr = 0.0 if hrr < 0.0 else (1.0 if hrr > 1.0 else hrr)
        total += (min(dt, ZONE_DT_CAP_S) / 60.0) * hrr * TRIMP_COEFF * math.exp(k * hrr)
        seen = True
    return total if seen else None


@dataclass(frozen=True, slots=True)
class LoadEstimate:
    """A load number that says where it came from (ADR-0008 §5)."""

    value: float
    basis: str  # "power+ftp" | "hr-trimp" | "hr-trimp (male-coefficient default)"
    components: dict[str, float]  # e.g. weighted_avg_power, intensity_ratio


def hr_coverage_fraction(session: Session) -> float | None:
    """Fraction of the session duration covered by present-HR sample pairs.
    None when there is no HR stream or no duration to compare against."""
    hr = session.records.stream("heart_rate")
    dur = _session_duration_s(session)
    if hr is None or not dur:
        return None
    covered = 0.0
    times = session.records.time
    for i in range(len(times) - 1):
        t0, t1 = times[i], times[i + 1]
        v = hr.values[i]
        if t0 is None or t1 is None or not isinstance(v, (int, float)) or isinstance(v, bool):
            continue
        dt = (t1 - t0).total_seconds()
        if dt > 0:
            covered += min(dt, ZONE_DT_CAP_S)
    return min(covered / dur, 1.0)


def _session_duration_s(session: Session) -> float | None:
    """Timer -> elapsed -> declared -> record span (derivable truth only)."""
    der, dec = session.derived, session.declared
    for v in (
        der.timer_time_s,
        der.elapsed_time_s,
        dec.timer_time_s if dec else None,
        dec.elapsed_time_s if dec else None,
    ):
        if v:
            return v
    times = [t for t in session.records.time if t is not None]
    if len(times) >= 2:
        span = (times[-1] - times[0]).total_seconds()
        return span if span > 0 else None
    return None


def workout_load(session: Session, settings: AthleteSettings | None) -> LoadEstimate | None:
    """Estimator ladder: power+ftp -> hr TRIMP -> None. A missing number
    beats an invented one; the report records the omission reason."""
    rec = session.records
    if settings is not None and settings.ftp_w:
        pw = rec.stream("power")
        if pw is not None:
            wap = weighted_avg_power(pw.values)
            dur = _session_duration_s(session)
            if wap is not None and dur:
                ir = intensity_ratio(wap, settings.ftp_w)
                return LoadEstimate(
                    value=load_score(dur, ir),
                    basis="power+ftp",
                    components={
                        "weighted_avg_power": wap,
                        "intensity_ratio": ir,
                        "duration_s": dur,
                    },
                )
    if settings is not None and settings.max_hr and settings.resting_hr:
        hr = rec.stream("heart_rate")
        cov = hr_coverage_fraction(session)
        if hr is not None and cov is not None and cov >= TRIMP_MIN_COVERAGE:
            t = trimp(
                rec.time,
                hr.values,
                resting_hr=settings.resting_hr,
                max_hr=settings.max_hr,
                sex=settings.sex,
            )
            if t is not None:
                basis = "hr-trimp" if settings.sex else "hr-trimp (male-coefficient default)"
                return LoadEstimate(
                    value=t,
                    basis=basis,
                    components={"max_hr": settings.max_hr, "resting_hr": settings.resting_hr},
                )
    return None


@dataclass(frozen=True, slots=True)
class FitnessPoint:
    """One day in the fitness/fatigue/form series.

    Attributes:
        day: The calendar day.
        load: Total load recorded that day (0 for rest days).
        fitness: 42-day exponentially-weighted load (long-term training).
        fatigue: 7-day exponentially-weighted load (short-term stress).
        form: ``fitness(t-1) - fatigue(t-1)`` — readiness, lagging a day.
    """

    day: date
    load: float  # total load that day
    fitness: float  # 42 d EW average of daily load
    fatigue: float  # 7 d EW average of daily load
    form: float  # fitness(t-1) - fatigue(t-1)


def fitness_fatigue_form(daily_loads: list[tuple[date, float]]) -> list[FitnessPoint]:
    """Impulse-response over a day series. Missing days count as 0 load.
    Seeds at 0 (an athlete's true starting fitness is unknowable from one
    archive slice — stated, not guessed)."""
    if not daily_loads:
        return []
    by_day: dict[date, float] = {}
    for d, v in daily_loads:
        by_day[d] = by_day.get(d, 0.0) + v
    first, last = min(by_day), max(by_day)
    k_fit = 1.0 - math.exp(-1.0 / FITNESS_TC_DAYS)
    k_fat = 1.0 - math.exp(-1.0 / FATIGUE_TC_DAYS)
    fitness = fatigue = 0.0
    out: list[FitnessPoint] = []
    day = first
    while day <= last:
        prev_fitness, prev_fatigue = fitness, fatigue
        load = by_day.get(day, 0.0)
        fitness += (load - fitness) * k_fit
        fatigue += (load - fatigue) * k_fat
        out.append(
            FitnessPoint(
                day=day,
                load=load,
                fitness=fitness,
                fatigue=fatigue,
                form=prev_fitness - prev_fatigue,
            )
        )
        day += timedelta(days=1)
    return out
