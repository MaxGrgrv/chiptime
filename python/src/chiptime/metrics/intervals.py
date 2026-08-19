"""Interval & structure detection — evidence ladder, deterministic bands.

Structure is a *reading* of the data: every result carries its evidence
basis, and "no clear structure" is a first-class answer (ADR-0008 §5/§6).
Ladder (research doc §10, platform survey §12): structured-workout steps →
manual laps → swim sets → band detection on the primary signal → none.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime

from chiptime.message import Message
from chiptime.metrics.pacing import format_pace, pace_seconds
from chiptime.metrics.settings import AthleteSettings
from chiptime.metrics.sports import PaceStyle, primary_signal, profile_for
from chiptime.model import Session

# --- detection constants (the TS port copies these verbatim) -------------
SMOOTH_WINDOW = 11  # rolling-median samples
REF_LOW_Q = 0.20  # band reference = midpoint of these two quantiles of
REF_HIGH_Q = 0.80  # positive smoothed samples (sits between effort levels)
WORK_BAND = 1.10  # smoothed >= band * working-median → work
RECOVERY_BAND = 0.85  # smoothed <= band * working-median → recovery
MIN_WORK_S = 20.0  # shorter work runs merge into neighbors
MIN_RECOVERY_S = 15.0
MIN_WORK_REPS = 3  # fewer → "none" (no clear structure)
MAX_DURATION_CV = 0.40  # work-duration spread beyond this → "none"
SWIM_SET_REST_MIN_S = 10.0  # wall rest below this joins lengths into one swim
REPEAT_DURATION_TOL = 0.25  # ±25% duration for repeat grouping
REPEAT_INTENSITY_TOL = 0.10  # ±10% intensity for repeat grouping

# workout_step.intensity → interval kind
_STEP_KIND = {
    "active": "work",
    "interval": "work",
    "rest": "rest",
    "recovery": "recovery",
    "warmup": "warmup",
    "cooldown": "cooldown",
}


@dataclass(frozen=True, slots=True)
class Interval:
    """One segment of the workout, in time order.

    Attributes:
        index: 1-based position.
        kind: ``work | recovery | rest | warmup | cooldown | steady``.
        start_time: Segment start.
        end_time: Segment end.
        duration_s: Length in seconds.
        distance_m: Distance covered, when a distance stream exists.
        avg_primary: Mean of the primary signal (W or m/s) over the segment.
        avg_hr: Mean heart rate, when present.
        lengths: Pool swims — lengths in this swim; None elsewhere.
        step_index: Structured workouts — the ``wkt_step_index`` this lap
            executed; None elsewhere.
    """

    index: int  # 1-based, in time order
    kind: str  # work|recovery|rest|warmup|cooldown|steady
    start_time: datetime | None
    end_time: datetime | None
    duration_s: float | None
    distance_m: float | None
    avg_primary: float | None  # mean of the primary signal (W or m/s)
    avg_hr: float | None
    lengths: int | None = None  # pool swims: lengths in this swim
    step_index: int | None = None  # structured workouts: wkt_step_index


@dataclass(frozen=True, slots=True)
class RepeatGroup:
    """N similar consecutive work intervals, in athlete notation.

    Attributes:
        count: Number of reps.
        kind: What repeats (``"work"``).
        mean_duration_s: Mean rep duration.
        mean_distance_m: Mean rep distance, when known.
        mean_primary: Mean intensity across reps (W or m/s).
        mean_rest_s: Mean recovery between reps, when detectable.
        label: The human line — ``"6 x 0:30 @ 300 W rest 0:30"``.
        first_index: ``Interval.index`` of the first rep.
    """

    count: int
    kind: str  # what repeats (always "work" today)
    mean_duration_s: float | None
    mean_distance_m: float | None
    mean_primary: float | None
    mean_rest_s: float | None  # mean recovery between reps; None if unknown
    label: str  # "6 x 0:30 @ 385 W", "10 x 100m @ 1:45/100m"
    first_index: int  # Interval.index of the first rep


@dataclass(frozen=True, slots=True)
class IntervalStructure:
    """The structure reading for one session — always with its evidence.

    Attributes:
        basis: Where the structure came from: ``steps:workout`` (structured
            workout), ``laps:manual`` (button presses), ``lengths:sets``
            (pool grouping), ``detected:power-steps`` /
            ``detected:speed-steps`` (band detection), or ``none``.
        intervals: The segments, in time order (empty for ``none``).
        repeats: Grouped "N x ..." patterns among the work intervals.
        note: For ``none``: the honest reason no structure was called.
    """

    basis: str  # steps:workout|laps:manual|lengths:sets|
    # detected:power-steps|detected:speed-steps|none
    intervals: tuple[Interval, ...] = ()
    repeats: tuple[RepeatGroup, ...] = ()
    note: str | None = None  # honest context, e.g. why detection declined


# --- helpers -------------------------------------------------------------


def _num(v: object) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _series(session: Session, name: str) -> list[tuple[float, datetime, float]]:
    """(t_rel_s, timestamp, value) for records where time+value are present."""
    s = session.records.stream(name)
    if s is None:
        return []
    out: list[tuple[float, datetime, float]] = []
    t0: datetime | None = None
    for i, t in enumerate(session.records.time):
        v = _num(s.values[i])
        if t is None or v is None:
            continue
        if t0 is None:
            t0 = t
        out.append(((t - t0).total_seconds(), t, v))
    return out


def _aggregate(
    session: Session, start: datetime, end: datetime, primary_stream: str | None
) -> tuple[float | None, float | None, float | None]:
    """(avg_primary, avg_hr, distance_m) over [start, end) from streams."""
    rec = session.records
    hr = rec.stream("heart_rate")
    prim = rec.stream(primary_stream) if primary_stream else None
    dist = rec.stream("distance")
    p_sum = p_n = h_sum = h_n = 0.0
    d_first: float | None = None
    d_last: float | None = None
    for i, t in enumerate(rec.time):
        if t is None or t < start or t >= end:
            continue
        if prim is not None:
            v = _num(prim.values[i])
            if v is not None:
                p_sum += v
                p_n += 1
        if hr is not None:
            v = _num(hr.values[i])
            if v is not None:
                h_sum += v
                h_n += 1
        if dist is not None:
            v = _num(dist.values[i])
            if v is not None:
                if d_first is None:
                    d_first = v
                d_last = v
    return (
        p_sum / p_n if p_n else None,
        h_sum / h_n if h_n else None,
        d_last - d_first if d_first is not None and d_last is not None else None,
    )


def _rolling_median(vals: list[float], window: int) -> list[float]:
    half = window // 2
    n = len(vals)
    return [statistics.median(vals[max(0, i - half) : min(n, i + half + 1)]) for i in range(n)]


def _lap_messages(messages: list[Message] | None) -> list[Message]:
    return [m for m in messages or [] if m.name == "lap"]


def _band_reference(values: list[float]) -> float:
    """Midpoint of the low/high quantiles of positive samples — a reference
    that sits *between* work and recovery levels, so both bands can fire
    regardless of which level dominates the file."""
    pos = sorted(v for v in values if v > 0)
    if not pos:
        return 0.0
    lo = pos[int(REF_LOW_Q * (len(pos) - 1))]
    hi = pos[int(REF_HIGH_Q * (len(pos) - 1))]
    return (lo + hi) / 2.0


def _classify_relative(avg: float | None, ref: float) -> str:
    if avg is None or ref <= 0:
        return "steady"
    if avg >= WORK_BAND * ref:
        return "work"
    if avg <= RECOVERY_BAND * ref:
        return "recovery"
    return "steady"


# --- ladder rungs --------------------------------------------------------


def _from_laps(
    session: Session, messages: list[Message], primary_stream: str | None
) -> IntervalStructure | None:
    """Structured-workout steps, else >=2 manual laps. None → next rung."""
    laps = _lap_messages(messages)
    if not laps:
        return None
    step_intensity: dict[int, str] = {}
    for m in messages:
        if m.name == "workout_step":
            idx = m.get("message_index")
            intensity = m.get("intensity")
            if isinstance(idx, int) and isinstance(intensity, str):
                step_intensity[idx] = intensity
    stepped = [m for m in laps if isinstance(m.get("wkt_step_index"), int)]
    manual = [m for m in laps if m.get("lap_trigger") == "manual"]
    if stepped:
        use, basis = laps, "steps:workout"
    elif len(manual) >= 2:  # single lap → ignore laps, auto-detect (survey §12)
        use, basis = laps, "laps:manual"
    else:
        return None

    # reference for relative work/recovery classification on manual laps
    per_lap: list[
        tuple[Message, float | None, float | None, float | None, datetime | None, datetime | None]
    ] = []
    for m in use:
        start = m.get("start_time")
        elapsed = _num(m.get("total_elapsed_time"))
        end: datetime | None = None
        if isinstance(start, datetime) and elapsed is not None:
            from datetime import timedelta

            end = start + timedelta(seconds=elapsed)
        avg_p: float | None = None
        avg_hr: float | None = None
        dist: float | None = None
        if isinstance(start, datetime) and end is not None:
            avg_p, avg_hr, dist = _aggregate(session, start, end, primary_stream)
        if avg_p is None:
            avg_p = (
                _num(m.get("avg_power"))
                if primary_stream == "power"
                else _num(m.get("avg_speed")) or _num(m.get("enhanced_avg_speed"))
            )
        if avg_hr is None:
            avg_hr = _num(m.get("avg_heart_rate"))
        if dist is None:
            dist = _num(m.get("total_distance"))
        per_lap.append(
            (m, avg_p, avg_hr, dist, start if isinstance(start, datetime) else None, end)
        )
    ref = _band_reference([v for _, v, _, _, _, _ in per_lap if v is not None])

    intervals: list[Interval] = []
    for i, (m, avg_p, avg_hr, dist, start, end) in enumerate(per_lap):
        step_idx = m.get("wkt_step_index")
        if basis == "steps:workout" and isinstance(step_idx, int):
            kind = _STEP_KIND.get(step_intensity.get(step_idx, ""), "steady")
        else:
            kind = _classify_relative(avg_p, ref)
        intervals.append(
            Interval(
                index=i + 1,
                kind=kind,
                start_time=start,
                end_time=end,
                duration_s=_num(m.get("total_timer_time")) or _num(m.get("total_elapsed_time")),
                distance_m=dist,
                avg_primary=avg_p,
                avg_hr=avg_hr,
                step_index=step_idx if isinstance(step_idx, int) else None,
            )
        )
    return IntervalStructure(
        basis=basis, intervals=tuple(intervals), repeats=_group_repeats(intervals, session)
    )


def _swim_sets(session: Session, messages: list[Message] | None) -> IntervalStructure | None:
    active = [ln for ln in session.lengths if (ln.length_type or "active") == "active"]
    if not active:
        return None
    pool_len: float | None = None
    for m in messages or []:
        if m.name == "session":
            pool_len = _num(m.get("pool_length"))
            if pool_len:
                break
    if not pool_len:
        d = session.derived.distance_m or (
            session.declared.distance_m if session.declared else None
        )
        pool_len = d / len(active) if d and active else None

    # group active lengths: wall rest below SWIM_SET_REST_MIN_S joins a swim
    groups: list[list[int]] = [[0]]
    for i in range(1, len(active)):
        prev_end = active[i - 1].end_time
        cur_start = active[i].start_time
        rest = (
            (cur_start - prev_end).total_seconds()
            if prev_end is not None and cur_start is not None
            else None
        )
        if rest is not None and rest < SWIM_SET_REST_MIN_S:
            groups[-1].append(i)
        else:
            groups.append([i])
    intervals: list[Interval] = []
    for gi, idxs in enumerate(groups):
        lens = [active[i] for i in idxs]
        dur = sum(ln.total_elapsed_time_s or 0.0 for ln in lens) or None
        if dur is None and lens[0].start_time and lens[-1].end_time:
            dur = (lens[-1].end_time - lens[0].start_time).total_seconds()
        dist = pool_len * len(lens) if pool_len else None
        speed = dist / dur if dist and dur else None
        intervals.append(
            Interval(
                index=gi + 1,
                kind="work",
                start_time=lens[0].start_time,
                end_time=lens[-1].end_time,
                duration_s=dur,
                distance_m=dist,
                avg_primary=speed,
                avg_hr=None,
                lengths=len(lens),
            )
        )
    return IntervalStructure(
        basis="lengths:sets", intervals=tuple(intervals), repeats=_group_repeats(intervals, session)
    )


def _detect(session: Session, primary_kind: str, primary_stream: str) -> IntervalStructure:
    series = _series(session, primary_stream)
    none = IntervalStructure(basis="none")
    if len(series) < SMOOTH_WINDOW:
        return IntervalStructure(basis="none", note="too little data to detect structure")
    smoothed = _rolling_median([v for _, _, v in series], SMOOTH_WINDOW)
    ref = _band_reference(smoothed)
    if ref <= 0:
        return none

    # hysteresis state machine → runs of (state, first_i, last_i)
    runs: list[tuple[str, int, int]] = []
    state = "recovery"
    for i, v in enumerate(smoothed):
        if v >= WORK_BAND * ref:
            new = "work"
        elif v <= RECOVERY_BAND * ref:
            new = "recovery"
        else:
            new = state  # hysteresis: between bands keeps the current state
        if runs and runs[-1][0] == new:
            runs[-1] = (new, runs[-1][1], i)
        else:
            runs.append((new, i, i))
        state = new

    def _dur(r: tuple[str, int, int]) -> float:
        return series[r[2]][0] - series[r[1]][0]

    # merge runs shorter than their minimum into the previous run (spike guard)
    merged: list[tuple[str, int, int]] = []
    for r in runs:
        min_s = MIN_WORK_S if r[0] == "work" else MIN_RECOVERY_S
        if merged and (_dur(r) < min_s or merged[-1][0] == r[0]):
            merged[-1] = (merged[-1][0], merged[-1][1], r[2])
        elif not merged and _dur(r) < min_s:
            merged.append(("recovery", r[1], r[2]))  # leading stub is warm-in
        else:
            merged.append(r)

    work_runs = [r for r in merged if r[0] == "work"]
    if len(work_runs) < MIN_WORK_REPS:
        return IntervalStructure(
            basis="none",
            note=f"{len(work_runs)} work efforts found; "
            f"need >= {MIN_WORK_REPS} similar reps to call it structure",
        )
    durs = [_dur(r) for r in work_runs]
    mean_d = sum(durs) / len(durs)
    cv = (statistics.pstdev(durs) / mean_d) if mean_d > 0 else 1.0
    if cv > MAX_DURATION_CV:
        return IntervalStructure(
            basis="none",
            note=f"work-effort durations too varied (CV {cv:.0%}) to call it interval structure",
        )

    intervals: list[Interval] = []
    for i, r in enumerate(merged):
        t_start, ts_start = series[r[1]][0], series[r[1]][1]
        ts_end = series[r[2]][1]
        avg_p, avg_hr, dist = _aggregate(session, ts_start, ts_end, primary_stream)
        intervals.append(
            Interval(
                index=i + 1,
                kind=r[0],
                start_time=ts_start,
                end_time=ts_end,
                duration_s=series[r[2]][0] - t_start,
                distance_m=dist,
                avg_primary=avg_p,
                avg_hr=avg_hr,
            )
        )
    basis = "detected:power-steps" if primary_kind == "power" else "detected:speed-steps"
    return IntervalStructure(
        basis=basis, intervals=tuple(intervals), repeats=_group_repeats(intervals, session)
    )


# --- repeat grouping -----------------------------------------------------


def _group_repeats(intervals: list[Interval], session: Session) -> tuple[RepeatGroup, ...]:
    """Consecutive similar work intervals → "N x ..." groups (>= 2 reps)."""
    style: PaceStyle = profile_for(session).pace_style
    groups: list[list[Interval]] = []
    rests: dict[int, float] = {}
    prev_work: Interval | None = None
    for iv in intervals:
        if iv.kind != "work":
            if (
                prev_work is not None
                and iv.kind in ("recovery", "rest")
                and iv.duration_s is not None
            ):
                rests[prev_work.index] = iv.duration_s
            continue
        if groups and _similar(groups[-1][0], iv):
            groups[-1].append(iv)
        else:
            groups.append([iv])
        prev_work = iv
    out: list[RepeatGroup] = []
    for g in groups:
        if len(g) < 2:
            continue
        durs = [iv.duration_s for iv in g if iv.duration_s is not None]
        dists = [iv.distance_m for iv in g if iv.distance_m is not None]
        prims = [iv.avg_primary for iv in g if iv.avg_primary is not None]
        rest_vals = [rests[iv.index] for iv in g if iv.index in rests]
        mean_dur = sum(durs) / len(durs) if durs else None
        mean_dist = sum(dists) / len(dists) if dists else None
        mean_prim = sum(prims) / len(prims) if prims else None
        mean_rest = sum(rest_vals) / len(rest_vals) if rest_vals else None
        out.append(
            RepeatGroup(
                count=len(g),
                kind="work",
                mean_duration_s=mean_dur,
                mean_distance_m=mean_dist,
                mean_primary=mean_prim,
                mean_rest_s=mean_rest,
                label=_label(
                    len(g),
                    mean_dur,
                    mean_dist,
                    mean_prim,
                    mean_rest,
                    style,
                    swim=g[0].lengths is not None,
                ),
                first_index=g[0].index,
            )
        )
    return tuple(out)


def _similar(a: Interval, b: Interval) -> bool:
    if a.lengths is not None and b.lengths is not None:  # swim: same rep distance
        return a.lengths == b.lengths
    if a.duration_s is None or b.duration_s is None:
        return False
    base = max(a.duration_s, b.duration_s)
    if base <= 0 or abs(a.duration_s - b.duration_s) / base > REPEAT_DURATION_TOL:
        return False
    if a.avg_primary is not None and b.avg_primary is not None:
        pbase = max(a.avg_primary, b.avg_primary)
        if pbase > 0 and abs(a.avg_primary - b.avg_primary) / pbase > REPEAT_INTENSITY_TOL:
            return False
    return True


def _fmt_mmss(seconds: float) -> str:
    total = int(seconds + 0.5)
    m, s = divmod(total, 60)
    return f"{m}:{s:02d}"


def _label(
    count: int,
    dur: float | None,
    dist: float | None,
    prim: float | None,
    rest: float | None,
    style: PaceStyle,
    *,
    swim: bool,
) -> str:
    if swim and dist is not None:
        head = f"{count} x {dist:.0f}m"
    elif dist is not None and dist >= 200 and style != "speed":
        head = f"{count} x {dist / 1000:.1f}km" if dist >= 950 else f"{count} x {dist:.0f}m"
    elif dur is not None:
        head = f"{count} x {_fmt_mmss(dur)}"
    else:
        head = f"{count} x ?"
    at = ""
    if prim is not None:
        if style == "speed":
            at = f" @ {prim:.0f} W"
        else:
            pace = format_pace(pace_seconds(prim, style), style, suffix=True)
            at = f" @ {pace}" if pace else ""
    tail = f" rest {_fmt_mmss(rest)}" if rest is not None else ""
    return head + at + tail


# --- entry point ---------------------------------------------------------


def detect_structure(
    session: Session, messages: list[Message] | None = None, settings: AthleteSettings | None = None
) -> IntervalStructure:
    """Evidence ladder: workout steps → manual laps → swim sets → band
    detection → none. `messages` (from ParseResult.messages) unlocks the lap
    and workout-step rungs and pool length; without it those rungs are
    skipped (declared honestly in the note)."""
    del settings  # reserved: zone-based classification (BACKLOG)
    profile = profile_for(session)
    kind, stream = primary_signal(session)
    if messages:
        by_laps = _from_laps(session, messages, stream)
        if by_laps is not None:
            return by_laps
    if profile.distance_from_lengths:
        by_lengths = _swim_sets(session, messages)
        if by_lengths is not None:
            return by_lengths
    if kind == "none" or stream is None:
        return IntervalStructure(basis="none", note="no intensity stream to detect from")
    return _detect(session, kind, stream)
