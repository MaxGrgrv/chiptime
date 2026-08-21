"""Crop an activity without letting the file lie about itself (F27).

Removing records is easy; the hard part is that every number computed *from*
those records — session totals, activity totals, averages — is wrong the
moment they disappear. A trimmed file with stale totals is worse than an
untrimmed one, because the error is invisible and travels downstream forever.

So trimming here is two acts: filter the records, then rebuild everything
that depended on them, using the same semantic layer that computes totals
during a normal parse. There is no second implementation of totals
arithmetic to drift.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import chiptime
from chiptime.decode import FIT_EPOCH_UNIX
from chiptime.encode import EncodableMessage, encodable_from_message, encode_messages
from chiptime.errors import Diagnostic, FitError, ProvenanceEntry
from chiptime.message import Message
from chiptime.repair import _summary_message
from chiptime.result import Mode, ParseResult
from chiptime.semantics import build_activity

Source = Any

RECORD, LAP, SESSION, EVENT, ACTIVITY, LENGTH = 20, 19, 18, 21, 34, 101

# Messages whose content is derived from records; always rebuilt after a trim
_REBUILT = (SESSION, ACTIVITY)

_RELATIVE = re.compile(r"^([+-])(\d+(?:\.\d+)?)([smh]?)$")
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "": 1}


class TrimError(FitError):
    """A trim cannot be performed; no bytes are written."""


@dataclass(slots=True)
class TrimResult:
    """The cropped file plus an account of what was removed and rebuilt.

    Attributes:
        data: The trimmed ``.fit`` bytes.
        provenance: What was dropped and what was rebuilt, with counts.
        records_kept: Records inside the keep-window.
        records_dropped: Records removed by the trim.
        warnings: Non-fatal observations carried from the rebuild.
        output_strict_ok: Self-check — the output re-parsed in strict mode.
        parse_result: The parse of the *input*, for inspection.
    """

    data: bytes
    provenance: list[ProvenanceEntry] = field(default_factory=list)
    records_kept: int = 0
    records_dropped: int = 0
    warnings: list[Diagnostic] = field(default_factory=list)
    output_strict_ok: bool = False
    parse_result: ParseResult | None = None


def _prov(code: str, scope: str, detail: str, data: dict[str, Any]) -> ProvenanceEntry:
    return ProvenanceEntry(code=code, action="dropped", scope=scope, detail=detail, data=data)


def _to_fit_seconds(dt: datetime) -> int:
    return int(dt.timestamp()) - FIT_EPOCH_UNIX


def _resolve_bound(value: datetime | str | int | None, first: int, last: int) -> int | None:
    """Resolve a bound to FIT seconds.

    Accepts an absolute ``datetime``, an ISO-8601 string, or a relative
    offset — ``"+5m"`` meaning five minutes after the activity starts,
    ``"-10m"`` meaning ten minutes before it ends. One model covers "cut the
    warm-up" and "cut the drive home" alike.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return _to_fit_seconds(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    text = str(value).strip()
    rel = _RELATIVE.match(text)
    if rel is not None:
        sign, amount, unit = rel.groups()
        seconds = int(float(amount) * _UNIT_SECONDS[unit])
        return first + seconds if sign == "+" else last - seconds
    try:
        return _to_fit_seconds(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        raise TrimError(
            "TRIM_BAD_BOUND",
            f"cannot interpret {value!r} as a time bound",
            suggestion="use an ISO timestamp, or a relative offset like '+5m' or '-10m'",
        ) from None


def _activity_bounds(messages: list[Message]) -> tuple[int, int]:
    """Time span of the trimmable content: records, or pool lengths for
    length-only swim files (which carry no record messages at all)."""
    stamps: list[int] = []
    for m in messages:
        if m.global_num not in (RECORD, LENGTH):
            continue
        ts = m.get_raw("timestamp")
        if isinstance(ts, int) and not isinstance(ts, bool):
            stamps.append(ts)
    if not stamps:
        raise TrimError(
            "TRIM_NO_RECORDS",
            "the file has no timestamped records or lengths to trim",
            suggestion="run `chiptime parse` to see what the file actually contains",
        )
    return min(stamps), max(stamps)


def _lap_span(m: Message) -> tuple[int, int] | None:
    start = m.get_raw("start_time")
    elapsed = m.get("total_elapsed_time")
    if not isinstance(start, int):
        return None
    if isinstance(elapsed, (int, float)):
        return start, start + int(elapsed)  # end = start + elapsed, never the write ts (#50)
    end = m.get_raw("timestamp")
    return (start, end) if isinstance(end, int) else None


def trim(
    src: Source,
    *,
    after: datetime | str | int | None = None,
    before: datetime | str | int | None = None,
    mode: Mode = "lenient",
) -> TrimResult:
    """Crop an activity to a time window and rebuild every derived number.

    Args:
        src: Path, bytes, or binary file object.
        after: Keep records at or after this bound. Absolute ``datetime`` /
            ISO string, or relative: ``"+5m"`` = five minutes after the start
            (i.e. cut the first five minutes).
        before: Keep records at or before this bound. ``"-10m"`` = ten
            minutes before the end (i.e. cut the last ten minutes).
        mode: Parse policy for reading the input.

    Returns:
        `TrimResult` with the cropped bytes, provenance, kept/dropped counts,
        and the strict-mode self-check verdict.

    Raises:
        TrimError: no bound given, a bound cannot be interpreted, the file has
            no records, or the window keeps nothing. No bytes are written.
    """
    if after is None and before is None:
        raise TrimError(
            "TRIM_NO_WINDOW",
            "trim() was called without a window",
            suggestion="pass after= and/or before=, e.g. after='+5m'",
        )

    parsed = chiptime.parse(src, mode=mode)
    messages = list(parsed.messages)
    if not any(m.global_num == RECORD for m in messages):
        # Length-only pool files carry no records, so there is nothing to
        # rebuild session totals *from* once the stale summary is dropped —
        # and carrying a stale summary forward is the lie this feature
        # exists to prevent. Real watches write records alongside lengths.
        raise TrimError(
            "TRIM_NO_RECORDS",
            "this file has no record messages, so trimmed totals could not be "
            "recomputed (length-only pool files are not trimmable yet)",
            suggestion="run `chiptime parse` to see what the file contains; no bytes were written",
        )
    first, last = _activity_bounds(messages)
    lo = _resolve_bound(after, first, last)
    hi = _resolve_bound(before, first, last)
    lo = first if lo is None else max(lo, first)
    hi = last if hi is None else min(hi, last)
    if lo > hi:
        raise TrimError(
            "TRIM_EMPTY_RESULT",
            f"the requested window keeps nothing (after={after!r}, before={before!r})",
            suggestion="widen the window; no bytes were written",
        )

    prov: list[ProvenanceEntry] = []
    kept: list[Message] = []
    dropped_records = dropped_lengths = 0
    dropped_laps: list[int] = []
    kept_lap_indices: list[int] = []
    kept_events = 0

    for m in messages:
        gnum = m.global_num
        if gnum in _REBUILT:
            continue  # always rebuilt from survivors — never carried over stale
        if gnum in (RECORD, LENGTH, EVENT):
            ts = m.get_raw("timestamp")
            inside = isinstance(ts, int) and lo <= ts <= hi
            if inside:
                kept.append(m)
                kept_events += gnum == EVENT
            elif gnum == RECORD:
                dropped_records += 1
            elif gnum == LENGTH:
                dropped_lengths += 1
            continue
        if gnum == LAP:
            span = _lap_span(m)
            idx = m.get("message_index")
            if span is not None and lo <= span[0] and span[1] <= hi:
                kept.append(m)  # wholly inside: its declared totals are still true
                if isinstance(idx, int):
                    kept_lap_indices.append(idx)
            else:
                dropped_laps.append(idx if isinstance(idx, int) else -1)
            continue
        kept.append(m)

    records_kept = sum(1 for m in kept if m.global_num == RECORD)
    lengths_kept = sum(1 for m in kept if m.global_num == LENGTH)
    if not records_kept and not lengths_kept:
        raise TrimError(
            "TRIM_EMPTY_RESULT",
            "the requested window keeps no records or lengths",
            suggestion="widen the window; no bytes were written",
        )

    if dropped_records or dropped_lengths:
        prov.append(
            _prov(
                "TRIM_RECORDS_DROPPED",
                "file",
                f"dropped {dropped_records} record(s)"
                + (f" and {dropped_lengths} pool length(s)" if dropped_lengths else "")
                + " outside the requested window",
                {
                    "records_dropped": dropped_records,
                    "lengths_dropped": dropped_lengths,
                    "window_fit_seconds": [lo, hi],
                },
            )
        )
    if dropped_laps:
        prov.append(
            _prov(
                "TRIM_LAP_DROPPED",
                "file",
                f"dropped {len(dropped_laps)} lap(s) not wholly inside the window; "
                "their in-window records are kept",
                {"lap_message_indices": dropped_laps},
            )
        )

    # Rebuild derived totals from the survivors using the ordinary semantic
    # layer — the one place totals arithmetic lives (critique: no round trip).
    warnings: list[Diagnostic] = []
    rebuild_prov: list[ProvenanceEntry] = []
    activity = build_activity(kept, warnings, rebuild_prov, "trim")
    if not activity.sessions:
        raise TrimError(
            "TRIM_EMPTY_RESULT",
            "no session could be rebuilt from the surviving records",
            suggestion="widen the window; no bytes were written",
        )
    session = activity.sessions[0]

    tail: list[EncodableMessage] = []
    if not kept_events:
        tail.append(
            chiptime.encode.encodable_from_profile(
                EVENT, {"timestamp": lo, "event": "timer", "event_type": "start"}
            )
        )
        tail.append(
            chiptime.encode.encodable_from_profile(
                EVENT, {"timestamp": hi, "event": "timer", "event_type": "stop_all"}
            )
        )
    if not kept_lap_indices:
        tail.append(_summary_message(LAP, session, lo, hi, lap=True))
    tail.append(
        _summary_message(
            SESSION,
            session,
            lo,
            hi,
            lap=False,
            first_lap_index=min(kept_lap_indices) if kept_lap_indices else 0,
            num_laps=len(kept_lap_indices) or 1,
        )
    )
    timer = session.derived.timer_time_s or session.derived.elapsed_time_s
    activity_values: dict[str, object] = {
        "timestamp": hi,
        "num_sessions": 1,
        "type": "manual",
        "event": "activity",
        "event_type": "stop",
    }
    if timer is not None:
        activity_values["total_timer_time"] = timer
    tail.append(chiptime.encode.encodable_from_profile(ACTIVITY, activity_values))
    prov.append(
        ProvenanceEntry(
            code="TRIM_SUMMARIES_REBUILT",
            action="synthesized",
            scope="file",
            detail=(
                "session and activity totals recomputed from the "
                f"{records_kept or lengths_kept} surviving "
                f"{'record' if records_kept else 'length'}(s)"
            ),
            data={"records_kept": records_kept, "lengths_kept": lengths_kept},
        )
    )

    data = encode_messages([encodable_from_message(m) for m in kept] + tail)
    try:
        chiptime.parse(data, mode="strict")
        strict_ok = True
    except FitError:
        strict_ok = False
    return TrimResult(
        data=data,
        provenance=prov,
        records_kept=records_kept,
        records_dropped=dropped_records,
        warnings=warnings,
        output_strict_ok=strict_ok,
        parse_result=parsed,
    )
