"""Errors, diagnostics, provenance, and the machine-readable code registry.

Contract #5: every failure carries a stable code + human sentence + suggestion.
Contract #1: every drop/repair/reinterpretation is a ProvenanceEntry.
ADR-0003: decode emits Defect values; only the API boundary raises.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["fatal", "structural", "data"]
Action = Literal["dropped", "repaired", "synthesized", "reinterpreted", "ignored"]


@dataclass(frozen=True, slots=True)
class Defect:
    """An in-stream problem found while decoding. Never an exception (ADR-0003)."""

    code: str
    detail: str
    offset: int
    severity: Severity


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """A non-fatal observation surfaced to the user (warnings[])."""

    code: str
    detail: str
    scope: str


@dataclass(frozen=True, slots=True)
class ProvenanceEntry:
    """A record of something chiptime dropped, repaired, synthesized, or reinterpreted."""

    code: str
    action: Action
    scope: str
    detail: str
    byte_offset: int | None = None
    data: dict[str, Any] = field(default_factory=dict)


class FitError(Exception):
    """Base error. In strict mode these raise; in lenient/forensic they collect."""

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        byte_offset: int | None = None,
        suggestion: str | None = None,
    ) -> None:
        super().__init__(f"{code}: {detail}" + (f" — {suggestion}" if suggestion else ""))
        self.code = code
        self.detail = detail
        self.byte_offset = byte_offset
        self.suggestion = suggestion


class NotFitError(FitError): ...


class EmptyFileError(FitError): ...


class HeaderError(FitError): ...


class TruncatedError(FitError): ...


class CrcMismatchError(FitError): ...


class ProtocolError(FitError): ...


# ── code registry ───────────────────────────────────────────────────────────
# Single source of truth; docs/for-agents.md is generated from these tables.

ERROR_CODES: dict[str, str] = {
    "TIME_SHIFT_OUT_OF_RANGE": "A requested time shift would push a timestamp outside the "
    "representable FIT range (or onto the invalid sentinel); no bytes were written.",
    "FIT_EMPTY": "The file contains no bytes.",
    "FIT_TOO_SMALL": "The file is smaller than any valid FIT header.",
    "FIT_NO_CONTENT": "Structurally valid container, zero messages; data genuinely absent (#16).",
    "NOT_FIT_FORMAT": "The content is not FIT (detail names what it looks like).",
    "FIT_HEADER_INVALID": "The file header is malformed (size, magic, or fields).",
    "FIT_HEADER_CRC_MISMATCH": "The 14-byte header's CRC is nonzero and wrong.",
    "FIT_TRUNCATED": "The file ends before its declared content is complete.",
    "FIT_CRC_MISSING": "The 2-byte file CRC trailer is absent.",
    "FIT_CRC_MISMATCH": "The file CRC does not match the content.",
    "FIT_DATA_SIZE_MISMATCH": "The header's data_size disagrees with the actual bytes.",
    "FIT_UNDEFINED_LOCAL_TYPE": "A data message references a local type with no definition.",
    "FIT_DEFINITION_INVALID": "A definition message is malformed.",
    "FIT_FIELD_SIZE_INVALID": "A field's size is not a multiple of its base type size.",
    "FIT_BASE_TYPE_INVALID": "A definition declares an unknown base type.",
    "FIT_MISSING_TIMESTAMP_ANCHOR": "A compressed-timestamp record has no timestamp anchor.",
    "FIT_TRAILING_JUNK": "Bytes after the final CRC are not a chained FIT file.",
    "REPAIR_NOTHING_TO_SALVAGE": "Nothing usable survives parsing; repair refuses to"
    " fabricate data (#16).",
}

# Warnings reuse defect codes where a defect was "seen and continued" — the
# location (warnings[] vs errors[]) tells the treatment; the code stays stable.
WARNING_CODES: dict[str, str] = {
    "SPORT_PAIR_IMPLAUSIBLE": "Sport was edited while a non-generic sub-sport was left in "
    "place; verify the pair is what you intended (chiptime never guesses a replacement).",
    "FIT_CRC_MISMATCH": "File CRC is wrong but content decodes; continued.",
    "FIT_HEADER_CRC_MISMATCH": "Header CRC is wrong; continued.",
    "FIT_HEADER_INVALID": "Header is nonstandard; continued on best interpretation.",
    "FIT_CRC_MISSING": "File CRC trailer absent; content used as-is.",
    "FIT_DATA_SIZE_MISMATCH": "Header data_size is wrong; trusting actual content.",
    "FIT_MISSING_TIMESTAMP_ANCHOR": "Compressed timestamps had no anchor; those stamps absent.",
    "STRING_DECODE_REPLACED": "A string field contained invalid UTF-8; replacements used.",
    "STRING_UNTERMINATED": "A string field had no NUL terminator; whole buffer used.",
    "NONFINITE_FLOAT_NULLED": "A float field carried NaN/Infinity; treated as absent.",
    "RELATIVE_TIMESTAMP": "A date_time value is device-relative (< 0x10000000), not absolute.",
    "FIT_TRAILING_JUNK": "Bytes after the final CRC are not a chained FIT file; ignored.",
    "COMPRESSED_AND_EXPLICIT_TIMESTAMP": "Record had both timestamp forms; explicit kept.",
    "DEV_FIELD_NAME_SYNTHESIZED": "Developer field lacked usable metadata; name synthesized,"
    " data kept.",
    "DEV_DATA_ID_MISSING": "field_description references a developer_data_index that was"
    " never announced.",
    "DEV_INDEX_REDEFINED": "A developer_data_index was redefined mid-file by another app.",
    "ENHANCED_PAIR_DISAGREES": "speed/altitude and their enhanced_ twins disagree; enhanced kept.",
    "RECORDS_OUTSIDE_SESSIONS": "Records fall outside every session's bounds; attached to nearest.",
    "LOCAL_TIMESTAMP_IMPLAUSIBLE": "activity.local_timestamp is impossible for any real"
    " timezone (Zwift 1989 bug class).",
    "UNRELIABLE_ABSOLUTE_TIME": "Timestamps predate 2010; device likely never got GPS"
    " time. Relative timeline kept.",
    "TIMESTAMPS_AFTER_CREATION": "Records postdate file_id.time_created by more than 7"
    " days; device clock suspect.",
    "TIMER_STOP_WITHOUT_START": "Timer stop event had no preceding start; interval opened"
    " at first record.",
    "SUMMARY_AVG_EXCEEDS_MAX": "A declared average exceeds its declared maximum (#93).",
    "SUMMARY_NEGATIVE_TOTAL": "A declared total is negative (#93).",
    "ZERO_DURATION_SESSION": "Session declares zero duration but contains records (#97).",
    "MOVEMENT_WITHOUT_DISTANCE": "Speed present but distance never advances (#97).",
    "ACTIVITY_MESSAGE_MISSING": "No activity message present (#96); repair can synthesize.",
    "NUM_SESSIONS_MISMATCH": "activity.num_sessions disagrees with actual session count.",
    "HR_IMPLAUSIBLE": "Heart-rate samples above the physiological ceiling; flagged (#62).",
    "HR_FLATLINE": "Heart rate flatlined for 2+ minutes; sensor suspect (#62).",
    "POWER_IMPLAUSIBLE": "Power above 2500 W; flagged, never removed (#63).",
    "DISTANCE_DECREASES": "Distance stream decreases (#59).",
    "DISTANCE_RESET": "Distance resets to zero mid-activity (#59).",
    "DISTANCE_FROZEN": "Distance frozen while moving; dead distance source (#59).",
    "POOL_ZERO_LENGTH": "Active pool lengths under 2 s; push-off artifacts (#73).",
    "POOL_LENGTH_IMPLAUSIBLE": "Distance/lengths imply an implausible pool size (#73).",
    "LAP_ZERO_DURATION": "Zero-duration laps; double button press (#94).",
    "LAP_COVERAGE_GAP": "Laps do not cover the session span (#94).",
    "TIMESTAMP_DECLARED_AS_BYTES": "Field 253 declared as byte[4]; reassembled"
    " (Xiaomi-pipeline class).",
    "HR_EXPANSION_NO_ANCHOR": "hr.event_timestamp_12 appeared before any full"
    " event_timestamp; samples not expandable.",
}

PROVENANCE_CODES: dict[str, str] = {
    "SPORT_EDITED": "Declared sport/sub-sport rewritten at the user's explicit request.",
    "DEVICE_EDITED": "Declared recording-device identity rewritten at the user's explicit request.",
    "TIMESTAMPS_SHIFTED": "Every profile-typed timestamp shifted by a user-supplied offset.",
    "TRUNCATED_TAIL_SALVAGED": "File ends mid-content; complete records before the cut kept.",
    "STREAM_STOPPED_AT_DEFECT": "Decoding stopped at a structural defect; prefix salvaged.",
    "PARTIAL_RECORD_DISCARDED": "Trailing bytes formed an incomplete record; discarded.",
    "FIELD_RAW_SALVAGED": "Field bytes undecodable as declared type; raw bytes kept.",
    "TIMESTAMP_ANCHOR_FROM_FILE_ID": "Compressed timestamps anchored from file_id.time_created.",
    "PII_STRIPPED": "Personally identifying content removed (strip_pii=True).",
    "UNKNOWN_MESSAGES_OMITTED": "Unknown-message content omitted (include_unknown=False).",
    "ZIP_ENTRIES_CHAINED": "Multiple .fit entries in a zip parsed as chained parts.",
    "RESYNC_SKIPPED_BYTES": "Undecodable bytes skipped; decoding resumed at the next"
    " plausible definition frame.",
    "PREAMBLE_GARBAGE_SKIPPED": "Garbage before the FIT header skipped; header re-anchored.",
    "DEV_FIELD_RESOLVED_LATE": "Developer fields re-resolved after their field_description"
    " arrived later in the file.",
    "ENHANCED_PAIR_MERGED": "enhanced_speed/altitude merged into the base stream"
    " (enhanced preferred, taxonomy #28).",
    "RECORDS_REORDERED": "Records were not in chronological order; stably sorted (ADR-0005 §1).",
    "TIMER_STOP_SYNTHESIZED": "No final timer stop; timer closed at the last record.",
    "SESSION_REBUILT": "No session message; session synthesized from records (#95).",
    "GPS_SPIKES_DROPPED": "Physically impossible GPS bounce spikes removed (lenient) or"
    " flagged (forensic) (#53).",
    "NULL_ISLAND_DROPPED": "Records at exactly (0,0) nulled or flagged (#51).",
    "VIRTUAL_GPS_EXEMPT": "Virtual-world coordinates exempt from plausibility gating (#57).",
    "REPAIR_FILE_ID_SYNTHESIZED": "Repair synthesized a missing file_id message.",
    "REPAIR_EVENTS_SYNTHESIZED": "Repair synthesized timer start/stop events (#96).",
    "REPAIR_LAP_SYNTHESIZED": "Repair synthesized one covering lap.",
    "REPAIR_SESSION_SYNTHESIZED": "Repair synthesized the session message from records (#95).",
    "REPAIR_ACTIVITY_SYNTHESIZED": "Repair synthesized the activity message (#96).",
    "REPAIR_REENCODED": "Repair re-encoded the file canonically; CRCs recomputed.",
    "REPAIR_LOCAL_TIMESTAMP_DROPPED": "Implausible local_timestamp not re-emitted"
    " (Zwift bug class, #37).",
}

_DEFECT_ERROR_CLASS: dict[str, type[FitError]] = {
    "FIT_EMPTY": EmptyFileError,
    "FIT_TOO_SMALL": NotFitError,
    "NOT_FIT_FORMAT": NotFitError,
    "FIT_HEADER_INVALID": HeaderError,
    "FIT_HEADER_CRC_MISMATCH": CrcMismatchError,
    "FIT_TRUNCATED": TruncatedError,
    "FIT_CRC_MISSING": TruncatedError,
    "FIT_CRC_MISMATCH": CrcMismatchError,
    "FIT_DATA_SIZE_MISMATCH": HeaderError,
    "FIT_UNDEFINED_LOCAL_TYPE": ProtocolError,
    "FIT_DEFINITION_INVALID": ProtocolError,
    "FIT_FIELD_SIZE_INVALID": ProtocolError,
    "FIT_BASE_TYPE_INVALID": ProtocolError,
    "FIT_MISSING_TIMESTAMP_ANCHOR": ProtocolError,
    "FIT_TRAILING_JUNK": ProtocolError,
}


def defect_to_error(defect: Defect, *, suggestion: str | None = None) -> FitError:
    cls = _DEFECT_ERROR_CLASS.get(defect.code, ProtocolError)
    return cls(defect.code, defect.detail, byte_offset=defect.offset, suggestion=suggestion)
