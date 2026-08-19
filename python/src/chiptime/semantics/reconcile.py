"""Declared-vs-derived reconciliation (#92), sanity flags (#93/#97),
ascent/descent derivation. Discrepancies are exposed, never auto-corrected."""

from __future__ import annotations

from itertools import pairwise

from chiptime.errors import Diagnostic
from chiptime.model import Discrepancy, Session

ASCENT_HYSTERESIS_M = 3.0
HR_CEILING_BPM = 230.0
HR_FLATLINE_S = 120
POWER_CEILING_W = 2500.0
LAP_COVERAGE_MIN = 0.9
FROZEN_MIN_RUN = 30  # consecutive records (F19 real-ride finding)
FROZEN_SPEED_FLOOR = 2.0  # m/s: above walking pace

# field -> (absolute floor, relative band)
_TOTALS_TOL: dict[str, tuple[float, float]] = {
    "elapsed_time_s": (2.0, 0.02),
    "timer_time_s": (2.0, 0.02),
    "distance_m": (10.0, 0.02),
    "ascent_m": (10.0, 0.15),
    "descent_m": (10.0, 0.15),
}
_AVGMAX_TOL: dict[str, tuple[float, float]] = {
    "heart_rate": (2.0, 0.03),
    "power": (5.0, 0.05),
    "speed": (0.2, 0.03),
    "cadence": (2.0, 0.05),
}


def derive_ascent_descent(s: Session) -> None:
    alt = s.records.stream("altitude")
    if alt is None:
        return
    up = down = 0.0
    ref: float | None = None
    for v in alt.values:
        if not isinstance(v, (int, float)):
            continue
        f = float(v)
        if ref is None:
            ref = f
            continue
        d = f - ref
        if d >= ASCENT_HYSTERESIS_M:
            up += d
            ref = f
        elif d <= -ASCENT_HYSTERESIS_M:
            down += -d
            ref = f
    if ref is not None:
        s.derived.ascent_m = up
        s.derived.descent_m = down


def reconcile(s: Session, warnings: list[Diagnostic], scope: str) -> None:
    d = s.declared
    if d is None:
        return

    for fname, (floor, rel) in _TOTALS_TOL.items():
        dec = getattr(d, fname)
        der = getattr(s.derived, fname)
        _compare(s, fname, dec, der, floor, rel)
    for key, (floor, rel) in _AVGMAX_TOL.items():
        _compare(s, f"avg.{key}", d.avg.get(key), s.derived.avg.get(key), floor, rel)
        _compare(s, f"max.{key}", d.max.get(key), s.derived.max.get(key), floor, rel)

    for key in sorted(set(d.avg) & set(d.max)):
        if d.avg[key] > d.max[key]:
            warnings.append(
                Diagnostic(
                    "SUMMARY_AVG_EXCEEDS_MAX",
                    f"declared avg {key} ({d.avg[key]}) exceeds declared max"
                    f" ({d.max[key]}) — summary untrustworthy (taxonomy #93)",
                    scope,
                )
            )
    for fname in ("elapsed_time_s", "timer_time_s", "distance_m", "calories_kcal"):
        v = getattr(d, fname)
        if v is not None and v < 0:
            warnings.append(
                Diagnostic(
                    "SUMMARY_NEGATIVE_TOTAL",
                    f"declared {fname} is negative ({v})",
                    scope,
                )
            )

    n = s.records.n
    if d.elapsed_time_s == 0 and n > 0:
        warnings.append(
            Diagnostic(
                "ZERO_DURATION_SESSION",
                f"session declares zero duration but contains {n} record(s) (taxonomy #97)",
                scope,
            )
        )
    avg_speed = s.derived.avg.get("speed")
    der_dist = s.derived.distance_m
    if n > 0 and avg_speed is not None and avg_speed > 1.0 and (der_dist is None or der_dist < 1.0):
        warnings.append(
            Diagnostic(
                "MOVEMENT_WITHOUT_DISTANCE",
                f"speed stream averages {avg_speed:.1f} m/s but the distance stream"
                f" never advances (taxonomy #97; dead distance source?)",
                scope,
            )
        )


def sensor_flags(s: Session, warnings: list[Diagnostic], scope: str) -> None:
    """HR/power physiological gates (#62/#63) and distance anomalies (#59).
    Flags only — interpolation is opt-in repair territory (BACKLOG)."""
    hr = s.records.stream("heart_rate")
    if hr is not None:
        nums = [v for v in hr.values if isinstance(v, (int, float))]
        high = sum(1 for v in nums if v > HR_CEILING_BPM)
        if high:
            warnings.append(
                Diagnostic(
                    "HR_IMPLAUSIBLE",
                    f"{high} heart-rate sample(s) above {HR_CEILING_BPM:.0f} bpm"
                    f" (strap static / contact class, #62)",
                    scope,
                )
            )
        run = best = 0
        prev: object = None
        for v in hr.values:
            if v is not None and v == prev:
                run += 1
                best = max(best, run)
            else:
                run = 0
            prev = v
        if best >= HR_FLATLINE_S:
            warnings.append(
                Diagnostic(
                    "HR_FLATLINE",
                    f"heart rate flatlined for {best + 1} consecutive record(s) (#62)",
                    scope,
                )
            )
    power = s.records.stream("power")
    if power is not None:
        high = sum(1 for v in power.values if isinstance(v, (int, float)) and v > POWER_CEILING_W)
        if high:
            warnings.append(
                Diagnostic(
                    "POWER_IMPLAUSIBLE",
                    f"{high} power sample(s) above {POWER_CEILING_W:.0f} W (#63);"
                    f" flagged, not removed — sprints are real",
                    scope,
                )
            )
    dist = s.records.stream("distance")
    if dist is not None:
        vals = [(i, float(v)) for i, v in enumerate(dist.values) if isinstance(v, (int, float))]
        decreases = resets = 0
        for (_, a), (_, b) in pairwise(vals):
            if b < a:
                if b < 1.0 and a > 10.0:
                    resets += 1
                else:
                    decreases += 1
        if decreases:
            warnings.append(
                Diagnostic(
                    "DISTANCE_DECREASES",
                    f"distance stream decreases {decreases} time(s) (#59)",
                    scope,
                )
            )
        if resets:
            warnings.append(
                Diagnostic(
                    "DISTANCE_RESET",
                    f"distance stream resets to zero {resets} time(s) mid-activity (#59)",
                    scope,
                )
            )
        speed = s.records.stream("speed")
        # Swims legitimately freeze distance between lengths/fixes (#56/#73);
        # everywhere else, only a LONG consecutive run at real speed is a dead
        # sensor — short freezes at ~1 m/s are ride starts and junctions
        # (F19 finding on a real Wahoo ROAM ride: 3 runs, max 12 s, all benign).
        if speed is not None and len(vals) >= 2 and s.sport != "swimming":
            run = longest = 0
            for k in range(1, len(vals)):
                (_, d0), (i1, d1) = vals[k - 1], vals[k]
                v = speed.values[i1]
                if d1 == d0 and isinstance(v, (int, float)) and v > FROZEN_SPEED_FLOOR:
                    run += 1
                    longest = max(longest, run)
                else:
                    run = 0
            if longest >= FROZEN_MIN_RUN:
                warnings.append(
                    Diagnostic(
                        "DISTANCE_FROZEN",
                        f"distance frozen for {longest} consecutive record(s) while"
                        f" moving faster than {FROZEN_SPEED_FLOOR} m/s (dead distance"
                        f" source, #59)",
                        scope,
                    )
                )


def swim_checks(s: Session, warnings: list[Diagnostic], scope: str) -> None:
    """Pool-swim semantics (#73): lengths x pool size vs declared distance."""
    if not s.lengths:
        return
    zero = sum(
        1
        for ln in s.lengths
        if ln.length_type == "active"
        and ln.total_elapsed_time_s is not None
        and ln.total_elapsed_time_s < 2.0
    )
    if zero:
        warnings.append(
            Diagnostic(
                "POOL_ZERO_LENGTH",
                f"{zero} active length(s) under 2 s (wall push-off artifacts, #73)",
                scope,
            )
        )
    # pool_length lives on the session message; reachable via declared distance check
    active = sum(1 for ln in s.lengths if ln.length_type == "active")
    if active and s.declared is not None and s.declared.distance_m:
        implied = s.declared.distance_m / active
        if not 15.0 <= implied <= 55.0:
            warnings.append(
                Diagnostic(
                    "POOL_LENGTH_IMPLAUSIBLE",
                    f"declared distance / {active} active lengths implies a"
                    f" {implied:.1f} m pool (mis-set pool size class, #73 — flaggable,"
                    f" not fixable)",
                    scope,
                )
            )


def lap_checks(s: Session, warnings: list[Diagnostic], scope: str) -> None:
    """Lap defects (#94): zero duration, coverage gaps."""
    zero = sum(1 for lap in s.laps if lap.declared is not None and lap.declared.elapsed_time_s == 0)
    if zero:
        warnings.append(
            Diagnostic(
                "LAP_ZERO_DURATION",
                f"{zero} zero-duration lap(s) (double lap-button press, #94)",
                scope,
            )
        )
    if s.laps and s.derived.elapsed_time_s:
        covered = sum(
            lap.declared.elapsed_time_s or 0.0 for lap in s.laps if lap.declared is not None
        )
        if covered < LAP_COVERAGE_MIN * s.derived.elapsed_time_s:
            warnings.append(
                Diagnostic(
                    "LAP_COVERAGE_GAP",
                    f"laps cover {covered:.0f}s of a {s.derived.elapsed_time_s:.0f}s session (#94)",
                    scope,
                )
            )


def _compare(
    s: Session,
    fname: str,
    dec: float | None,
    der: float | None,
    floor: float,
    rel: float,
) -> None:
    if dec is None or der is None:
        return
    delta = der - dec
    if abs(delta) > max(floor, rel * abs(dec)):
        s.discrepancies.append(Discrepancy(fname, dec, der, delta))
