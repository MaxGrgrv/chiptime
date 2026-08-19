"""Assemble the canonical Activity model from decoded messages.

Order-independent by construction (contract #9): everything is bucketed first,
then bound by time — never by position in the file. Summary-first and
summary-last layouts produce identical models.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from chiptime.decode import FIT_EPOCH_UNIX, RELATIVE_TS_CEILING
from chiptime.errors import Diagnostic, ProvenanceEntry
from chiptime.message import Message
from chiptime.model import (
    Activity,
    AthleteProfile,
    DeviceInfo,
    Event,
    Lap,
    Length,
    Records,
    Session,
    Stream,
    Totals,
)
from chiptime.semantics.gaps import classify_gaps
from chiptime.semantics.plausibility import gate_positions
from chiptime.semantics.reconcile import (
    derive_ascent_descent,
    lap_checks,
    reconcile,
    sensor_flags,
    swim_checks,
)
from chiptime.semantics.timers import build_timer_state, moving_seconds

FLOOR_2010_FIT = 631238400  # 2010-01-01T00:00:00Z in FIT seconds
CREATION_DRIFT_MAX_S = 7 * 86400  # ADR-0005 §2
MAX_REAL_OFFSET_S = 26 * 3600  # ADR-0005 §4

# Streams where element-wise avg/max is meaningless.
_AVGMAX_EXCLUDE = {"position_lat", "position_long", "distance", "activity_type"}

_ENHANCED_PAIRS = [("speed", "enhanced_speed"), ("altitude", "enhanced_altitude")]


def _dt(fit_seconds: object) -> datetime | None:
    if not isinstance(fit_seconds, int):
        return None
    if fit_seconds < RELATIVE_TS_CEILING:
        # device-relative (power-on) time is NOT a date; resurrecting it from
        # raws would fabricate 1990 wall-clock times (F22, fitparse#3/#6)
        return None
    return datetime.fromtimestamp(FIT_EPOCH_UNIX + fit_seconds, tz=UTC)


def _num(v: object) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _sport_str(v: object) -> str:
    if isinstance(v, str):
        return v
    if v is None:
        return "unknown"
    return f"unknown_{v}"


def build_activity(
    messages: list[Message],
    warnings: list[Diagnostic],
    provenance: list[ProvenanceEntry],
    scope: str,
    *,
    skipped_ranges: list[tuple[int, int]] | None = None,
    forensic: bool = False,
) -> Activity:
    records = [m for m in messages if m.global_num == 20]
    records = _sorted_records(records, provenance, scope)
    _time_sanity_flags(records, messages, warnings, scope)
    session_msgs = [m for m in messages if m.global_num == 18]
    lap_msgs = [m for m in messages if m.global_num == 19]
    length_msgs = [m for m in messages if m.global_num == 101]
    event_msgs = [m for m in messages if m.global_num == 21]

    activity = Activity()

    for m in messages:
        if m.global_num == 23 and activity.device is None:
            activity.device = DeviceInfo(
                manufacturer=m.get("manufacturer"),
                product=m.get("product"),
                product_name=m.get("product_name"),
                serial_number=m.get("serial_number"),
                software_version=_num(m.get("software_version")),
            )
        elif m.global_num == 3 and activity.athlete is None:
            activity.athlete = AthleteProfile(
                friendly_name=m.get("friendly_name"),
                gender=m.get("gender"),
                age=m.get("age"),
                weight_kg=_num(m.get("weight")),
                height_m=_num(m.get("height")),
            )
        elif m.global_num == 34 and activity.local_timestamp is None:
            lt = m.get("local_timestamp")
            activity.local_timestamp = lt if isinstance(lt, str) else None
            _local_offset(m, activity, warnings, scope)

    for m in messages:
        if m.global_num == 78:  # hrv: RR interval arrays, never dropped (#72)
            t = m.get("time")
            if isinstance(t, list):
                activity.hrv_intervals_s.extend(float(v) for v in t if isinstance(v, (int, float)))
            elif isinstance(t, (int, float)):
                activity.hrv_intervals_s.append(float(t))

    activity.events = [
        Event(
            time=_dt(m.get_raw("timestamp")),
            event=m.get("event"),
            event_type=m.get("event_type"),
            data=m.get("data") if isinstance(m.get("data"), int) else None,
        )
        for m in event_msgs
    ]

    sessions = [_session_shell(m) for m in session_msgs]
    sessions.sort(key=lambda s: (s.start_time is None, s.start_time))
    if not sessions and records:
        # Session rebuild (#95) — the repair every crashed upload needs.
        sport_msg = next((m for m in messages if m.global_num == 12), None)
        first = _dt(records[0].get_raw("timestamp"))
        last = _dt(records[-1].get_raw("timestamp"))
        sessions = [
            Session(
                sport=_sport_str(sport_msg.get("sport")) if sport_msg else "unknown",
                sub_sport=None,
                start_time=first,
                end_time=last,
                declared=None,
                rebuilt=True,
            )
        ]
        provenance.append(
            ProvenanceEntry(
                "SESSION_REBUILT",
                "synthesized",
                scope,
                f"no session message present; session synthesized from {len(records)} record(s)",
                data={"records": len(records)},
            )
        )
    if not sessions:
        return activity  # nothing to model (honest: no fake sessions, #8/#16)

    if session_msgs and not any(m.global_num == 34 for m in messages):
        warnings.append(
            Diagnostic(
                "ACTIVITY_MESSAGE_MISSING",
                "no activity message present (taxonomy #96); repair (M2) can synthesize one",
                scope,
            )
        )
    declared_n = next((m.get("num_sessions") for m in messages if m.global_num == 34), None)
    if isinstance(declared_n, int) and declared_n != len(sessions):
        warnings.append(
            Diagnostic(
                "NUM_SESSIONS_MISMATCH",
                f"activity declares {declared_n} session(s); file contains {len(sessions)}",
                scope,
            )
        )

    buckets = _assign(records, lap_msgs, length_msgs, sessions, warnings)

    for s, bucket in zip(sessions, buckets, strict=True):
        s.records = _build_streams(bucket, warnings, provenance, scope)
        ev = _session_events(activity.events, s, len(sessions))
        times = s.records.time
        first_t = next((t for t in times if t is not None), None)
        last_t = next((t for t in reversed(times) if t is not None), None)
        state = build_timer_state(ev, first_t, last_t, warnings, provenance, scope)
        s.derived.timer_time_s = state.timer_seconds()
        speed = s.records.stream("speed")
        s.derived.moving_time_s = moving_seconds(times, speed.values if speed else None, state)
        activity.gaps.extend(
            classify_gaps(times, [m.byte_offset for m in bucket], state, ev, skipped_ranges or [])
        )
        _derive(s)
        _derive_relative_elapsed(s, bucket)
        manufacturer = next((m.get("manufacturer") for m in messages if m.global_num == 0), None)
        gate_positions(
            s,
            forensic=forensic,
            virtual=(manufacturer == "zwift" or s.sub_sport == "virtual_activity"),
            provenance=provenance,
            scope=scope,
        )
        derive_ascent_descent(s)
        reconcile(s, warnings, scope)
        sensor_flags(s, warnings, scope)
        swim_checks(s, warnings, scope)
        lap_checks(s, warnings, scope)

    activity.sessions = sessions
    return activity


def _sorted_records(
    records: list[Message], provenance: list[ProvenanceEntry], scope: str
) -> list[Message]:
    """ADR-0005 §1: stable sort with carry-forward keys; reorders recorded."""
    last = -1
    is_sorted = True
    for m in records:
        ts = m.get_raw("timestamp")
        if isinstance(ts, int):
            if ts < last:
                is_sorted = False
                break
            last = ts
    if is_sorted:  # F20: the overwhelmingly common case, one cheap scan
        return records
    keys: list[tuple[int, int]] = []
    last = -1
    for i, m in enumerate(records):
        ts = m.get_raw("timestamp")
        if isinstance(ts, int):
            last = ts
        keys.append((last, i))
    order = sorted(range(len(records)), key=lambda i: keys[i])
    if order == list(range(len(records))):
        return records
    moved = sum(1 for pos, i in enumerate(order) if pos != i)
    provenance.append(
        ProvenanceEntry(
            "RECORDS_REORDERED",
            "reinterpreted",
            scope,
            f"{moved} record(s) were out of chronological order; stably sorted"
            f" (equal timestamps keep file order)",
            data={"moved": moved},
        )
    )
    return [records[i] for i in order]


def _time_sanity_flags(
    records: list[Message],
    messages: list[Message],
    warnings: list[Diagnostic],
    scope: str,
) -> None:
    raws = [
        ts
        for m in records
        if isinstance(ts := m.get_raw("timestamp"), int) and ts >= RELATIVE_TS_CEILING
    ]
    if not raws:
        return
    if min(raws) < FLOOR_2010_FIT:
        warnings.append(
            Diagnostic(
                "UNRELIABLE_ABSOLUTE_TIME",
                "record timestamps predate 2010; the device likely never acquired"
                " GPS time — relative timeline preserved (ADR-0005 §3)",
                scope,
            )
        )
    created = next((m.get_raw("time_created") for m in messages if m.global_num == 0), None)
    if isinstance(created, int) and max(raws) > created + CREATION_DRIFT_MAX_S:
        warnings.append(
            Diagnostic(
                "TIMESTAMPS_AFTER_CREATION",
                "record timestamps postdate file_id.time_created by more than 7 days;"
                " device clock suspect (ADR-0005 §2)",
                scope,
            )
        )


def _local_offset(m: Message, activity: Activity, warnings: list[Diagnostic], scope: str) -> None:
    """ADR-0005 §4: validate the local/UTC pair (taxonomy #37, Zwift 1989 bug)."""
    ts_raw = m.get_raw("timestamp")
    lt_raw = m.get_raw("local_timestamp")
    if not isinstance(lt_raw, int) or not isinstance(ts_raw, int):
        return
    if lt_raw == 0xFFFFFFFF or ts_raw == 0xFFFFFFFF:
        return  # sentinel = honestly absent, not implausible
    if lt_raw < RELATIVE_TS_CEILING or ts_raw < RELATIVE_TS_CEILING:
        warnings.append(
            Diagnostic(
                "LOCAL_TIMESTAMP_IMPLAUSIBLE",
                f"activity.local_timestamp raw {lt_raw} is device-relative"
                f" (the Zwift 1989 bug class); utc offset unavailable",
                scope,
            )
        )
        return
    off = lt_raw - ts_raw
    if abs(off) > MAX_REAL_OFFSET_S:
        warnings.append(
            Diagnostic(
                "LOCAL_TIMESTAMP_IMPLAUSIBLE",
                f"local-UTC offset of {off} s is impossible for any real timezone",
                scope,
            )
        )
        return
    activity.utc_offset_s = off


def _session_events(events: list[Event], s: Session, n_sessions: int) -> list[Event]:
    if n_sessions == 1 or s.start_time is None or s.end_time is None:
        return events
    return [e for e in events if e.time is not None and s.start_time <= e.time <= s.end_time]


def _session_shell(m: Message) -> Session:
    start = _dt(m.get_raw("start_time"))
    elapsed = _num(m.get("total_elapsed_time"))
    end = None
    if start is not None and elapsed is not None:
        # #50: end = start + elapsed. The summary's own timestamp is a WRITE
        # time and must never define bounds.
        end = datetime.fromtimestamp(start.timestamp() + elapsed, tz=UTC)
    declared = Totals(
        elapsed_time_s=elapsed,
        timer_time_s=_num(m.get("total_timer_time")),
        distance_m=_num(m.get("total_distance")),
        ascent_m=_num(m.get("total_ascent")),
        descent_m=_num(m.get("total_descent")),
        calories_kcal=_num(m.get("total_calories")),
    )
    for key, avg_f, max_f in (
        ("speed", "avg_speed", "max_speed"),
        ("heart_rate", "avg_heart_rate", "max_heart_rate"),
        ("cadence", "avg_cadence", "max_cadence"),
        ("power", "avg_power", "max_power"),
    ):
        av = _num(m.get(f"enhanced_{avg_f}")) if key == "speed" else None
        av = av if av is not None else _num(m.get(avg_f))
        mx = _num(m.get(f"enhanced_{max_f}")) if key == "speed" else None
        mx = mx if mx is not None else _num(m.get(max_f))
        if av is not None:
            declared.avg[key] = av
        if mx is not None:
            declared.max[key] = mx
    return Session(
        sport=_sport_str(m.get("sport")),
        sub_sport=m.get("sub_sport") if isinstance(m.get("sub_sport"), str) else None,
        start_time=start,
        end_time=end,
        declared=declared,
    )


def _assign(
    records: list[Message],
    lap_msgs: list[Message],
    length_msgs: list[Message],
    sessions: list[Session],
    warnings: list[Diagnostic],
) -> list[list[Message]]:
    buckets: list[list[Message]] = [[] for _ in sessions]

    def owner(t: datetime | None) -> int:
        if len(sessions) == 1 or t is None:
            return 0
        for i, s in enumerate(sessions):
            if s.start_time and s.end_time and s.start_time <= t <= s.end_time:
                return i
        # nearest by start (F9 formalizes multisport leftovers with provenance)
        return min(
            range(len(sessions)),
            key=lambda i: (
                abs((t - sessions[i].start_time).total_seconds())  # type: ignore[operator]
                if sessions[i].start_time
                else 1e18
            ),
        )

    outside = 0
    for m in records:
        t = _dt(m.get_raw("timestamp"))
        i = owner(t)
        s = sessions[i]
        in_bounds = bool(
            t is not None and s.start_time and s.end_time and s.start_time <= t <= s.end_time
        )
        if len(sessions) > 1 and t is not None and not in_bounds:
            outside += 1
        buckets[i].append(m)
    if outside:
        warnings.append(
            Diagnostic(
                "RECORDS_OUTSIDE_SESSIONS",
                f"{outside} record(s) fall outside every session's declared bounds;"
                f" attached to the nearest session",
                "activity",
            )
        )

    for m in lap_msgs:
        start = _dt(m.get_raw("start_time"))
        elapsed = _num(m.get("total_elapsed_time"))
        end = (
            datetime.fromtimestamp(start.timestamp() + elapsed, tz=UTC)
            if start is not None and elapsed is not None
            else None
        )
        mi = m.get("message_index")
        lap = Lap(
            message_index=mi if isinstance(mi, int) else None,
            start_time=start,
            end_time=end,
            declared=Totals(
                elapsed_time_s=elapsed,
                timer_time_s=_num(m.get("total_timer_time")),
                distance_m=_num(m.get("total_distance")),
                calories_kcal=_num(m.get("total_calories")),
            ),
            sport=m.get("sport") if isinstance(m.get("sport"), str) else None,
        )
        sessions[owner(start)].laps.append(lap)

    for m in length_msgs:
        start = _dt(m.get_raw("start_time"))
        elapsed = _num(m.get("total_elapsed_time"))
        end = (
            datetime.fromtimestamp(start.timestamp() + elapsed, tz=UTC)
            if start is not None and elapsed is not None
            else None
        )
        strokes = m.get("total_strokes")
        sessions[owner(start)].lengths.append(
            Length(
                start_time=start,
                end_time=end,
                length_type=m.get("length_type") if isinstance(m.get("length_type"), str) else None,
                swim_stroke=m.get("swim_stroke") if isinstance(m.get("swim_stroke"), str) else None,
                total_strokes=strokes if isinstance(strokes, int) else None,
                total_elapsed_time_s=elapsed,
            )
        )

    return buckets


def _build_streams(
    records: list[Message],
    warnings: list[Diagnostic],
    provenance: list[ProvenanceEntry],
    scope: str,
) -> Records:
    out = Records()
    order: list[str] = []  # first-appearance stream order (deterministic)
    meta: dict[str, tuple[str | None, str]] = {}
    columns: dict[str, list[Any]] = {}

    for i, m in enumerate(records):
        out.time.append(_dt(m.get_raw("timestamp")))
        for fname, fv in m.fields.items():
            if fname == "timestamp":
                continue
            sname = fname
            source = "native"
            if fv.developer is not None:
                if fv.developer.canonical_name:
                    sname = fv.developer.canonical_name
                source = f"developer:{fv.developer.vendor}" if fv.developer.vendor else "developer"
            if sname in meta and meta[sname][1] != source:
                sname = f"{sname}_dev"
            if sname not in columns:
                order.append(sname)
                meta[sname] = (fv.units, source)
                columns[sname] = [None] * i
            value = fv.value.hex() if isinstance(fv.value, bytes) else fv.value
            columns[sname].append(value)
        for sname in order:
            if len(columns[sname]) <= i:
                columns[sname].append(None)

    _merge_enhanced(order, meta, columns, warnings, provenance, scope)

    for sname in order:
        units, source = meta[sname]
        out.streams[sname] = Stream(sname, units, columns[sname], source)
    return out


def _merge_enhanced(
    order: list[str],
    meta: dict[str, tuple[str | None, str]],
    columns: dict[str, list[Any]],
    warnings: list[Diagnostic],
    provenance: list[ProvenanceEntry],
    scope: str,
) -> None:
    """Taxonomy #28: one stream per quantity; enhanced wins; never both silently."""
    for base, enhanced in _ENHANCED_PAIRS:
        if enhanced not in columns:
            continue
        evals = columns.pop(enhanced)
        order.remove(enhanced)
        emeta = meta.pop(enhanced)
        if base not in columns:
            columns[base] = evals
            order.append(base)
            meta[base] = emeta
            continue
        bvals = columns[base]
        disagreements = 0
        merged: list[Any] = []
        for e, b in zip(evals, bvals, strict=True):
            both = isinstance(e, float) and isinstance(b, float)
            if both and abs(e - b) > 0.01:
                disagreements += 1
            merged.append(e if e is not None else b)
        columns[base] = merged
        if disagreements:
            warnings.append(
                Diagnostic(
                    "ENHANCED_PAIR_DISAGREES",
                    f"{base} and {enhanced} disagree on {disagreements} record(s);"
                    f" enhanced values kept",
                    scope,
                )
            )
        provenance.append(
            ProvenanceEntry(
                "ENHANCED_PAIR_MERGED",
                "reinterpreted",
                scope,
                f"{enhanced} merged into the {base} stream (enhanced preferred)",
                data={"disagreements": disagreements},
            )
        )


def _derive_relative_elapsed(s: Session, bucket: list[Message]) -> None:
    """Taxonomy #39: when the device never had wall-clock time (all timestamps
    device-relative), the RELATIVE timeline is still real — derive durations
    from raw deltas instead of leaving everything None (fitparse#3/#6 class)."""
    if s.derived.elapsed_time_s is not None:
        return
    raws = [
        ts for m in bucket if isinstance(ts := m.get_raw("timestamp"), int) and ts != 0xFFFFFFFF
    ]
    if len(raws) >= 2 and raws[-1] >= raws[0]:
        s.derived.elapsed_time_s = float(raws[-1] - raws[0])


def _derive(s: Session) -> None:
    times = [t for t in s.records.time if t is not None]
    if len(times) >= 2:
        s.derived.elapsed_time_s = (times[-1] - times[0]).total_seconds()
    dist = s.records.stream("distance")
    if dist is not None:
        present = [v for v in dist.values if isinstance(v, (int, float))]
        if len(present) >= 2:
            s.derived.distance_m = float(present[-1]) - float(present[0])
    for name, stream in s.records.streams.items():
        if name in _AVGMAX_EXCLUDE:
            continue
        nums = [v for v in stream.values if isinstance(v, (int, float)) and not isinstance(v, bool)]
        if nums:
            s.derived.avg[name] = sum(nums) / len(nums)
            s.derived.max[name] = float(max(nums))
