"""ParseResult and canonical output shaping (schema chiptime/1, ADR-0002)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from chiptime.canonical import MAX_SAFE_INT, dumps
from chiptime.errors import Diagnostic, FitError, ProvenanceEntry
from chiptime.message import Message

Mode = Literal["strict", "lenient", "forensic"]

SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SourceInfo:
    """Identity of the parsed input. The local ``path`` is kept for humans
    but never serialized (privacy + determinism, ADR-0002); ``sha256`` is
    the stable identity — cache and dedupe on it.

    Attributes:
        path: Where the bytes came from locally, or None for in-memory input.
        size_bytes: Input size after any unwrapping.
        sha256: Hash of the parsed bytes.
        unwrapped: Containers removed on the way in (``("gzip",)``, ...).
    """

    path: str | None  # never serialized (privacy + determinism, ADR-0002)
    size_bytes: int
    sha256: str
    unwrapped: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    """What salvage did, when it had to. Present on the result only if
    truncation recovery or resynchronization engaged — its absence means the
    file needed none.

    Attributes:
        recovered_records: Data messages decoded despite the damage.
        estimated_total_records: Best estimate of what a healthy file held.
        bytes_read: Bytes successfully consumed.
        bytes_skipped: Bytes stepped over as unreadable.
        resync_count: Times the reader re-anchored past corruption.
    """

    recovered_records: int  # decoded data messages (all types)
    estimated_total_records: int | None
    bytes_read: int
    bytes_skipped: int
    resync_count: int


@dataclass(slots=True)
class FitPart:
    """One FIT file within the source. Chained files (a device appending
    several FIT parts into one file) yield several parts; ``parse`` reports
    each separately rather than blending them.

    Attributes:
        file_type: ``"activity" | "course" | "workout" | "monitoring" | ...``
        file_id: Decoded file_id message fields, when present.
        messages: Every decoded message of this part, in file order.
        activity: The semantic `chiptime.model.Activity` for activity parts.
    """

    file_type: str
    file_id: dict[str, Any] | None
    messages: list[Message]
    activity: Any | None = None  # semantic model lands in F7


class ParseResult:
    """Everything `chiptime.parse` learned about one source.

    The navigation model: one call, then drill into plain data —
    ``result.activity.sessions[0].records.stream("power")``. Nothing here is
    lazy or stateful; what you see is the complete, final read.

    The paper trail is the other half: ``errors`` (what was wrong),
    ``warnings`` (what was suspicious), and ``provenance`` (every drop,
    repair, and reinterpretation chiptime performed). An empty paper trail
    means the file was exactly what it claimed to be.

    Attributes:
        ok: True when usable content was produced.
        mode: The policy used (``strict | lenient | forensic``).
        source: Input identity (`SourceInfo`).
        parts: One `FitPart` per FIT file found in the source.
        errors: Structural problems, as coded diagnostics.
        warnings: Suspicious-but-recoverable findings.
        provenance: The complete record of decisions taken on your data.
        recovery: `RecoveryReport` when salvage engaged, else None.
    """

    def __init__(
        self,
        *,
        ok: bool,
        mode: Mode,
        source: SourceInfo,
        parts: list[FitPart],
        provenance: list[ProvenanceEntry],
        warnings: list[Diagnostic],
        errors: list[FitError],
        recovery: RecoveryReport | None,
        include_raw: bool = False,
    ) -> None:
        self.ok = ok
        self.mode: Mode = mode
        self.source = source
        self.parts = parts
        self.provenance = provenance
        self.warnings = warnings
        self.errors = errors
        self.recovery = recovery
        self._include_raw = include_raw

    # ── conveniences (primary part = first activity part, else first) ────

    @property
    def _primary(self) -> FitPart | None:
        for p in self.parts:
            if p.file_type == "activity":
                return p
        return self.parts[0] if self.parts else None

    @property
    def file_type(self) -> str:
        p = self._primary
        return p.file_type if p else "unknown"

    @property
    def messages(self) -> list[Message]:
        p = self._primary
        return p.messages if p else []

    @property
    def activity(self) -> Any | None:
        p = self._primary
        return p.activity if p else None

    # ── canonical output ─────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "chiptime_schema": SCHEMA_VERSION,
            "ok": self.ok,
            "mode": self.mode,
            "source": {
                "sha256": self.source.sha256,
                "size_bytes": self.source.size_bytes,
                "unwrapped": list(self.source.unwrapped),
            },
            "parts": [self._part_dict(p) for p in self.parts],
            "errors": [
                {
                    "code": e.code,
                    "detail": e.detail,
                    "byte_offset": e.byte_offset,
                    "suggestion": e.suggestion,
                }
                for e in self.errors
            ],
            "warnings": [
                {"code": w.code, "detail": w.detail, "scope": w.scope} for w in self.warnings
            ],
            "provenance": [
                {
                    "code": p.code,
                    "action": p.action,
                    "scope": p.scope,
                    "detail": p.detail,
                    "byte_offset": p.byte_offset,
                    "data": {k: _json_safe(v) for k, v in sorted(p.data.items())},
                }
                for p in self.provenance
            ],
            "recovery": (
                None
                if self.recovery is None
                else {
                    "recovered_records": self.recovery.recovered_records,
                    "estimated_total_records": self.recovery.estimated_total_records,
                    "bytes_read": self.recovery.bytes_read,
                    "bytes_skipped": self.recovery.bytes_skipped,
                    "resync_count": self.recovery.resync_count,
                }
            ),
        }

    def to_canonical_json(self) -> bytes:
        return dumps(self.to_dict())

    def _part_dict(self, part: FitPart) -> dict[str, Any]:
        # With a semantic model, record messages live losslessly in streams —
        # every field (native, unknown, developer) becomes a stream column.
        msgs = part.messages
        if part.activity is not None:
            msgs = [m for m in msgs if m.global_num != 20]
        return {
            "file_type": part.file_type,
            "file_id": (
                None
                if part.file_id is None
                else {k: _json_safe(v) for k, v in part.file_id.items()}
            ),
            "activity": None if part.activity is None else _activity_dict(part.activity),
            "messages": [self._message_dict(m) for m in msgs],
        }

    def _message_dict(self, m: Message) -> dict[str, Any]:
        fields: dict[str, Any] = {}
        for fname, fv in m.fields.items():
            entry: dict[str, Any] = {"value": _json_safe(fv.value)}
            if fv.units is not None:
                entry["units"] = fv.units
            if self._include_raw:
                entry["raw"] = _json_safe(fv.raw)
            if fv.developer is not None:
                entry["developer"] = {
                    "developer_data_index": fv.developer.developer_data_index,
                    "field_definition_number": fv.developer.field_definition_number,
                    "application_id": fv.developer.application_id,
                    "vendor": fv.developer.vendor,
                    "canonical_name": fv.developer.canonical_name,
                }
            fields[fname] = entry
        return {
            "name": m.name,
            "global_num": m.global_num,
            "offset": m.byte_offset,
            "fields": fields,
        }


def _json_safe(v: Any) -> Any:
    """Bytes to hex; ints beyond 2^53-1 to decimal strings (ADR-0002)."""
    if isinstance(v, bytes):
        return v.hex()
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, int) and abs(v) > MAX_SAFE_INT:
        return str(v)
    if isinstance(v, list):
        return [_json_safe(x) for x in v]
    return v


def _iso(dt: Any) -> str | None:
    return None if dt is None else dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _totals_dict(t: Any) -> dict[str, Any]:
    return {
        "elapsed_time_s": t.elapsed_time_s,
        "timer_time_s": t.timer_time_s,
        "moving_time_s": t.moving_time_s,
        "distance_m": t.distance_m,
        "ascent_m": t.ascent_m,
        "descent_m": t.descent_m,
        "calories_kcal": t.calories_kcal,
        "avg": dict(sorted(t.avg.items())),
        "max": dict(sorted(t.max.items())),
    }


def _activity_dict(a: Any) -> dict[str, Any]:
    return {
        "local_timestamp": a.local_timestamp,
        "utc_offset_s": a.utc_offset_s,
        "hrv_intervals_s": list(a.hrv_intervals_s),
        "device": None
        if a.device is None
        else {
            "manufacturer": a.device.manufacturer,
            "product": a.device.product,
            "product_name": a.device.product_name,
            "serial_number": a.device.serial_number,
            "software_version": a.device.software_version,
        },
        "athlete": None
        if a.athlete is None
        else {
            "friendly_name": a.athlete.friendly_name,
            "gender": a.athlete.gender,
            "age": a.athlete.age,
            "weight_kg": a.athlete.weight_kg,
            "height_m": a.athlete.height_m,
        },
        "events": [
            {"time": _iso(e.time), "event": e.event, "event_type": e.event_type, "data": e.data}
            for e in a.events
        ],
        "gaps": [
            {
                "start": _iso(g.start),
                "end": _iso(g.end),
                "duration_s": g.duration_s,
                "kind": g.kind,
                "evidence": g.evidence,
            }
            for g in a.gaps
        ],
        "sessions": [
            {
                "sport": s.sport,
                "sub_sport": s.sub_sport,
                "start_time": _iso(s.start_time),
                "end_time": _iso(s.end_time),
                "rebuilt": s.rebuilt,
                "declared": None if s.declared is None else _totals_dict(s.declared),
                "derived": _totals_dict(s.derived),
                "discrepancies": [
                    {
                        "field": d.field,
                        "declared": d.declared,
                        "derived": d.derived,
                        "delta": d.delta,
                    }
                    for d in s.discrepancies
                ],
                "laps": [
                    {
                        "message_index": lap.message_index,
                        "start_time": _iso(lap.start_time),
                        "end_time": _iso(lap.end_time),
                        "sport": lap.sport,
                        "declared": None if lap.declared is None else _totals_dict(lap.declared),
                    }
                    for lap in s.laps
                ],
                "lengths": [
                    {
                        "start_time": _iso(ln.start_time),
                        "end_time": _iso(ln.end_time),
                        "length_type": ln.length_type,
                        "swim_stroke": ln.swim_stroke,
                        "total_strokes": ln.total_strokes,
                        "total_elapsed_time_s": ln.total_elapsed_time_s,
                    }
                    for ln in s.lengths
                ],
                "records": {
                    "n": s.records.n,
                    "time": [_iso(t) for t in s.records.time],
                    "streams": {
                        name: {
                            "units": st.units,
                            "source": st.source,
                            "values": [_json_safe(v) for v in st.values],
                        }
                        for name, st in sorted(s.records.streams.items())
                    },
                },
            }
            for s in a.sessions
        ],
    }
