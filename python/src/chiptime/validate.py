"""Platform validation profiles (taxonomy #99/#102).

Folk knowledge encoded as explicit checks — heuristic by nature, named and
versioned in the open so corrections are one-line PRs, not tribal lore.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import chiptime
from chiptime._api import Source

Platform = Literal["strict-spec", "garmin-connect", "strava"]
Level = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class Finding:
    """One platform-acceptance issue: a severity level, a stable code, and
    the human reason — encoding the checks that actually make uploads fail."""

    level: Level
    code: str
    detail: str


def validate(src: Source, platform: Platform = "strict-spec") -> list[Finding]:
    if platform == "strict-spec":
        return _strict_spec(src)
    result = chiptime.parse(src)
    if not result.ok:
        return [
            Finding(
                "error", "VAL_UNPARSEABLE", "file does not parse; run chiptime parse for details"
            )
        ]
    if platform == "garmin-connect":
        return _garmin_connect(result)
    return _strava(result)


def _strict_spec(src: Source) -> list[Finding]:
    try:
        result = chiptime.parse(src, mode="strict")
    except chiptime.FitError as e:
        return [Finding("error", "VAL_SPEC_VIOLATION", f"{e.code}: {e.detail}")]
    if not result.ok:
        return [Finding("error", "VAL_SPEC_VIOLATION", "no usable content")]
    return []


def _garmin_connect(result: chiptime.ParseResult) -> list[Finding]:
    """Documented GC rejection classes (#99): stricter than Strava."""
    out: list[Finding] = []
    part = result.parts[0] if result.parts else None
    fid = part.file_id if part else None
    if fid is None:
        out.append(Finding("error", "VAL_GC_NO_FILE_ID", "file_id message missing"))
    else:
        if fid.get("type") != "activity":
            out.append(
                Finding(
                    "error",
                    "VAL_GC_NOT_ACTIVITY",
                    f"file_id.type is {fid.get('type')!r}, not 'activity'",
                )
            )
        if fid.get("time_created") is None:
            out.append(Finding("error", "VAL_GC_NO_TIME_CREATED", "file_id.time_created missing"))
        if fid.get("manufacturer") is None:
            out.append(Finding("error", "VAL_GC_NO_MANUFACTURER", "file_id.manufacturer missing"))
    names = {m.name for m in result.messages}
    for need, code in (
        ("session", "VAL_GC_NO_SESSION"),
        ("activity", "VAL_GC_NO_ACTIVITY"),
        ("lap", "VAL_GC_NO_LAP"),
    ):
        if need not in names:
            out.append(Finding("error", code, f"no {need} message (GC requires one)"))
    if "event" not in names:
        out.append(
            Finding(
                "warning",
                "VAL_GC_NO_EVENTS",
                "no timer events; GC usually tolerates but flags this",
            )
        )
    a = result.activity
    if a is not None and a.sessions:
        if any(g.kind == "corruption" for g in a.gaps):
            out.append(
                Finding(
                    "warning",
                    "VAL_GC_CORRUPTION_GAPS",
                    "corruption gaps present; GC may truncate the activity",
                )
            )
        if any(p.code == "RECORDS_REORDERED" for p in result.provenance):
            out.append(
                Finding(
                    "warning",
                    "VAL_GC_NONMONOTONIC_SOURCE",
                    "source records were out of order (GC rejects"
                    " non-monotonic files; a chiptime repair re-emits sorted)",
                )
            )
    events = [m for m in (part.messages if part else []) if m.name == "event"]
    if events and not any("stop" in str(m.get("event_type") or "") for m in events):
        out.append(
            Finding(
                "warning",
                "VAL_GC_NO_TIMER_STOP",
                "activity has timer events but never a stop; Garmin Connect is reported to "
                "require a stop event (community-observed, not documented)",
            )
        )
    if any(w.code == "LOCAL_TIMESTAMP_IMPLAUSIBLE" for w in result.warnings):
        out.append(
            Finding(
                "error",
                "VAL_GC_LOCAL_TIMESTAMP",
                "implausible local_timestamp — the documented Zwift"
                " rejection class (#37); repair omits it",
            )
        )
    return out


def _strava(result: chiptime.ParseResult) -> list[Finding]:
    out: list[Finding] = []
    part = result.parts[0] if result.parts else None
    fid = part.file_id if part else None
    if fid is None or fid.get("type") != "activity":
        out.append(Finding("error", "VAL_STRAVA_NOT_ACTIVITY", "file_id.type=activity required"))
    a = result.activity
    n = sum(s.records.n for s in a.sessions) if a else 0
    if n == 0:
        out.append(Finding("error", "VAL_STRAVA_NO_RECORDS", "no records; Strava needs a timeline"))
    if a is not None and not any(not s.rebuilt for s in a.sessions):
        out.append(
            Finding(
                "warning",
                "VAL_STRAVA_NO_SESSION",
                "no session message; Strava usually accepts but computes its own totals",
            )
        )
    return out
