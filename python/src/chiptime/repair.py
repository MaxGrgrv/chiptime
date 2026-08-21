"""Repair: salvage → synthesize missing structure → valid canonical .fit.

Every synthesis lands in provenance (REPAIR_*). Genuinely absent data is
refused, never fabricated (taxonomy #16, contract #8).
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

import chiptime
from chiptime._api import Source
from chiptime.decode import RELATIVE_TS_CEILING
from chiptime.encode import (
    EncodableMessage,
    encodable_from_message,
    encodable_from_profile,
    encode_messages,
)
from chiptime.errors import FitError, ProvenanceEntry
from chiptime.message import Message
from chiptime.model import Session
from chiptime.result import ParseResult


class NotRepairableError(FitError):
    pass


@dataclass
class RepairResult:
    """A repaired file plus the proof of what repair did.

    Attributes:
        data: The complete, valid ``.fit`` bytes — write them to disk as-is.
        provenance: Every salvaged, synthesized, and dropped element.
        output_strict_ok: Self-check — the output re-parsed in strict mode.
        parse_result: The salvage parse of the *input*, for inspection.
    """

    data: bytes  # the repaired .fit bytes
    provenance: list[ProvenanceEntry] = field(default_factory=list)
    output_strict_ok: bool = False  # self-check: repaired file parses strictly
    parse_result: ParseResult | None = None  # the salvage parse of the input


def repair(src: Source, *, mode: chiptime.Mode = "lenient") -> RepairResult:
    parsed = chiptime.parse(src, mode=mode)
    part = next((p for p in parsed.parts if p.file_type == "activity"), None)
    if part is None or part.activity is None or not part.activity.sessions:
        raise NotRepairableError(
            "REPAIR_NOTHING_TO_SALVAGE",
            "no activity records or session survive parsing; the data is genuinely"
            " absent and will not be fabricated",
            suggestion="run `chiptime parse --mode forensic` to inspect what remains",
        )

    prov: list[ProvenanceEntry] = []
    msgs = list(part.messages)
    session = part.activity.sessions[0]

    def has(gnum: int) -> bool:
        return any(m.global_num == gnum for m in msgs)

    front: list[EncodableMessage] = []
    tail: list[EncodableMessage] = []

    # file_id (synthesize if absent — #102)
    file_id_msgs = [m for m in msgs if m.global_num == 0]
    first_t, last_t = _bounds(session, msgs)
    if not file_id_msgs:
        front.append(
            encodable_from_profile(
                0,
                {
                    "type": "activity",
                    "manufacturer": "development",
                    "time_created": first_t,
                },
            )
        )
        prov.append(
            _p("REPAIR_FILE_ID_SYNTHESIZED", "no file_id message; synthesized (type=activity)")
        )

    front.append(encodable_from_profile(49, {}))  # file_creator marker (empty is valid)

    if not has(21) and session.records.n:
        tail.append(
            encodable_from_profile(
                21,
                {
                    "timestamp": first_t,
                    "event": "timer",
                    "event_type": "start",
                },
            )
        )
        tail.append(
            encodable_from_profile(
                21,
                {
                    "timestamp": last_t,
                    "event": "timer",
                    "event_type": "stop_all",
                },
            )
        )
        prov.append(
            _p(
                "REPAIR_EVENTS_SYNTHESIZED",
                "no timer events; start/stop_all synthesized at record bounds",
            )
        )

    if not has(19):
        tail.append(_summary_message(19, session, first_t, last_t, lap=True))
        prov.append(_p("REPAIR_LAP_SYNTHESIZED", "no lap message; one covering lap synthesized"))

    if not has(18):
        tail.append(_summary_message(18, session, first_t, last_t, lap=False))
        prov.append(
            _p(
                "REPAIR_SESSION_SYNTHESIZED",
                f"no session message; synthesized from {session.records.n}"
                f" salvaged record(s) (#95)",
            )
        )

    if not has(34):
        timer = session.derived.timer_time_s or session.derived.elapsed_time_s
        values: dict[str, object] = {
            "timestamp": last_t,
            "num_sessions": 1,
            "type": "manual",
            "event": "activity",
            "event_type": "stop",
        }
        if timer is not None:
            values["total_timer_time"] = timer
        tail.append(encodable_from_profile(34, values))
        prov.append(_p("REPAIR_ACTIVITY_SYNTHESIZED", "no activity message; synthesized"))

    cleaned: list[Message] = []
    for m in sorted(msgs, key=lambda m: 0 if m.global_num == 0 else 1):
        if m.global_num == 34:
            m2 = _drop_bad_local_timestamp(m, prov)
            cleaned.append(m2)
        else:
            cleaned.append(m)
    body = [encodable_from_message(m) for m in cleaned]
    prov.append(_p("REPAIR_REENCODED", "re-encoded to canonical wire form; all CRCs recomputed"))

    data = encode_messages(
        (body[:1] if file_id_msgs else []) + front + (body[1:] if file_id_msgs else body) + tail
    )
    check = chiptime.parse(data, mode="strict")
    return RepairResult(data=data, provenance=prov, output_strict_ok=check.ok, parse_result=parsed)


def _p(code: str, detail: str) -> ProvenanceEntry:
    return ProvenanceEntry(code, "synthesized", "repair", detail)


def _drop_bad_local_timestamp(m: Message, prov: list[ProvenanceEntry]) -> Message:
    """#37 repair leg: never re-emit an impossible local_timestamp; an honest
    absence (invalid sentinel) beats a wrong-but-plausible value."""
    lt = m.fields.get("local_timestamp")
    ts = m.fields.get("timestamp")
    if lt is None or not isinstance(lt.raw, int) or lt.raw == 0xFFFFFFFF:
        return m
    bad = lt.raw < RELATIVE_TS_CEILING
    if not bad and ts is not None and isinstance(ts.raw, int):
        bad = abs(lt.raw - ts.raw) > 26 * 3600
    if not bad:
        return m
    fields = dict(m.fields)
    fields["local_timestamp"] = dataclasses.replace(lt, value=None, raw=None)
    prov.append(
        ProvenanceEntry(
            "REPAIR_LOCAL_TIMESTAMP_DROPPED",
            "dropped",
            "repair",
            f"activity.local_timestamp raw {lt.raw} is impossible for any real"
            f" timezone; omitted from the repaired file (GC rejection class, #37)",
        )
    )
    return dataclasses.replace(m, fields=fields)


def _bounds(session: Session, msgs: list[Message]) -> tuple[int, int]:
    times = [t for t in session.records.time if t is not None]
    if times:
        from chiptime.decode import FIT_EPOCH_UNIX

        f = int(times[0].timestamp()) - FIT_EPOCH_UNIX
        la = int(times[-1].timestamp()) - FIT_EPOCH_UNIX
        return f, la
    for m in msgs:  # summary-only activities: bounds from session message raws
        if m.global_num == 18:
            st = m.get_raw("start_time")
            ts = m.get_raw("timestamp")
            if isinstance(st, int):
                return st, ts if isinstance(ts, int) else st
    raise NotRepairableError("REPAIR_NOTHING_TO_SALVAGE", "no usable timestamps to anchor repair")


def _summary_message(
    gnum: int,
    s: Session,
    first_t: int,
    last_t: int,
    *,
    lap: bool,
    first_lap_index: int = 0,
    num_laps: int = 1,
) -> EncodableMessage:
    values: dict[str, object] = {
        "timestamp": last_t,
        "start_time": first_t,
        "message_index": 0,
        "event": "lap" if lap else "session",
        "event_type": "stop",
    }
    der = s.derived
    if der.elapsed_time_s is not None:
        values["total_elapsed_time"] = der.elapsed_time_s
    if (der.timer_time_s or der.elapsed_time_s) is not None:
        values["total_timer_time"] = der.timer_time_s or der.elapsed_time_s
    if der.distance_m is not None:
        values["total_distance"] = der.distance_m
    if not lap:
        if s.sport and not s.sport.startswith("unknown"):
            values["sport"] = s.sport
        for key, avg_name, max_name in (
            ("heart_rate", "avg_heart_rate", "max_heart_rate"),
            ("power", "avg_power", "max_power"),
            ("cadence", "avg_cadence", "max_cadence"),
        ):
            if key in der.avg:
                values[avg_name] = round(der.avg[key])
            if key in der.max:
                values[max_name] = round(der.max[key])
        if "speed" in der.avg:
            values["avg_speed"] = der.avg["speed"]
        if "speed" in der.max:
            values["max_speed"] = der.max["speed"]
        values["first_lap_index"] = first_lap_index
        values["num_laps"] = num_laps
    return encodable_from_profile(gnum, values)
