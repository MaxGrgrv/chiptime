"""parse() — the one-call entry point; iter_frames/iter_messages streaming layers.

Mode policy per ADR-0003: strict raises the first defect; lenient recovers and
records; forensic is lenient that never drops (divergence begins in F5/F10).
"""

from __future__ import annotations

import dataclasses
import hashlib
from collections.abc import Iterator
from os import PathLike
from pathlib import Path
from typing import Any, BinaryIO

from chiptime.decode import Decoder
from chiptime.errors import (
    Defect,
    Diagnostic,
    FitError,
    ProvenanceEntry,
    defect_to_error,
)
from chiptime.frames import (
    CrcFrame,
    DataFrame,
    EndOfStream,
    FileHeader,
    FrameEvent,
    SkippedBytes,
    read_stream,
)
from chiptime.intake import unwrap
from chiptime.message import FieldValue, Message
from chiptime.result import FitPart, Mode, ParseResult, RecoveryReport, SourceInfo
from chiptime.semantics import build_activity

Source = str | PathLike[str] | bytes | bytearray | BinaryIO

# Structural defects that do NOT stop the stream — they surface as warnings
# in lenient/forensic ("seen and continued").
_CONTINUE_CODES = {
    "FIT_HEADER_INVALID",
    "FIT_HEADER_CRC_MISMATCH",
    "FIT_CRC_MISMATCH",
    "FIT_CRC_MISSING",
    "FIT_DATA_SIZE_MISMATCH",
}

_SUGGESTIONS = {
    "NOT_FIT_FORMAT": "route this file to a parser for the named format",
    "FIT_TRUNCATED": 'rerun with mode="lenient" to salvage the decodable prefix',
    "FIT_CRC_MISMATCH": 'rerun with mode="lenient" to decode despite the bad CRC',
    "FIT_HEADER_CRC_MISMATCH": 'rerun with mode="lenient" to decode despite the bad header CRC',
    "FIT_UNDEFINED_LOCAL_TYPE": 'rerun with mode="lenient" to salvage the decodable prefix',
    "FIT_DEFINITION_INVALID": 'rerun with mode="lenient" to salvage the decodable prefix',
    "FIT_DATA_SIZE_MISMATCH": 'rerun with mode="lenient" to parse the actual content',
}

_PII_MESSAGES = {"user_profile"}
_PII_FIELDS = {"serial_number"}


def _read_source(src: Source) -> tuple[bytes, str | None]:
    if isinstance(src, (bytes, bytearray)):
        return bytes(src), None
    if isinstance(src, (str, PathLike)):
        p = Path(src)
        return p.read_bytes(), str(p)
    data = src.read()
    return bytes(data), getattr(src, "name", None)


def iter_frames(src: Source, *, mode: Mode = "lenient") -> Iterator[FrameEvent]:
    """Lossless wire-level frame events (forensics layer)."""
    data, _ = _read_source(src)
    offset = 0
    while offset < len(data):
        consumed = offset
        for ev in read_stream(data, offset=offset):
            if isinstance(ev, Defect) and mode == "strict":
                raise defect_to_error(ev, suggestion=_SUGGESTIONS.get(ev.code))
            if isinstance(ev, EndOfStream):
                consumed = ev.consumed
            yield ev
        if consumed <= offset or not _looks_like_header(data, consumed):
            break
        offset = consumed


def iter_messages(src: Source, *, mode: Mode = "lenient") -> Iterator[Message]:
    """Profile-applied message stream without building the semantic model."""
    decoder = Decoder()
    for ev in iter_frames(src, mode=mode):
        if isinstance(ev, DataFrame):
            yield decoder.decode(ev)


def _looks_like_header(data: bytes, offset: int) -> bool:
    if len(data) - offset < 12:
        return False
    return data[offset + 8 : offset + 12] == b".FIT" or data[offset] in (12, 14)


def parse(
    src: Source,
    *,
    mode: Mode = "lenient",
    strip_pii: bool = False,
    include_unknown: bool = True,
    include_raw: bool = False,
) -> ParseResult:
    """Parse a FIT source. lenient (default) recovers and annotates; strict
    raises the first FitError; forensic maximizes salvage and never drops."""
    raw, path = _read_source(src)
    source_hash = hashlib.sha256(raw).hexdigest()
    intake_result = unwrap(raw)
    data = intake_result.data
    source = SourceInfo(
        path=path,
        size_bytes=len(raw),
        sha256=source_hash,
        unwrapped=intake_result.unwrapped,
    )

    parts: list[FitPart] = []
    provenance: list[ProvenanceEntry] = list(intake_result.provenance)
    warnings: list[Diagnostic] = []
    errors: list[FitError] = []

    for d in intake_result.defects:
        if mode == "strict":
            raise defect_to_error(d, suggestion=_SUGGESTIONS.get(d.code))
        errors.append(defect_to_error(d, suggestion=_SUGGESTIONS.get(d.code)))
    if any(d.severity == "fatal" for d in intake_result.defects):
        return ParseResult(
            ok=False,
            mode=mode,
            source=source,
            parts=[],
            provenance=provenance,
            warnings=warnings,
            errors=errors,
            recovery=None,
            include_raw=include_raw,
        )
    total_recovered = 0
    total_skipped = 0
    resync_count = 0
    recovery_engaged = False
    est_total: int | None = None

    offset = 0
    part_index = 0
    while True:  # runs at least once so empty input still yields its defect
        decoder = Decoder()
        messages: list[Message] = []
        stream_defects: list[Defect] = []
        skips: list[SkippedBytes] = []
        header: FileHeader | None = None
        consumed = len(data)
        body_bytes_decoded = 0

        for ev in read_stream(data, offset=offset):
            if isinstance(ev, Defect):
                if mode == "strict":
                    raise defect_to_error(ev, suggestion=_SUGGESTIONS.get(ev.code))
                stream_defects.append(ev)
            elif isinstance(ev, SkippedBytes):
                skips.append(ev)
            elif isinstance(ev, DataFrame):
                messages.append(decoder.decode(ev))
                body_bytes_decoded = (
                    ev.offset
                    + 1
                    + len(ev.payload)
                    - (header.offset + header.size if header else offset)
                )
            elif isinstance(ev, FileHeader):
                header = ev
            elif isinstance(ev, CrcFrame):
                pass  # mismatch already surfaced as a Defect
            elif isinstance(ev, EndOfStream):
                consumed = ev.consumed

        decode_out = decoder.finish()
        messages = decode_out.messages  # finish() may rebuild (late dev-field back-fill)
        provenance.extend(decode_out.provenance)
        warnings.extend(decode_out.diagnostics)
        for d in decode_out.defects:  # data-severity defects from decoding
            if mode == "strict":
                raise defect_to_error(d, suggestion=_SUGGESTIONS.get(d.code))
            warnings.append(Diagnostic(d.code, d.detail, f"byte {d.offset}"))

        scope = f"part[{part_index}]"
        skip_offsets = {s.offset for s in skips}
        for skip in skips:
            recovery_engaged = True
            total_skipped += skip.length
            if skip.reason == "preamble-garbage":
                provenance.append(
                    ProvenanceEntry(
                        "PREAMBLE_GARBAGE_SKIPPED",
                        "repaired",
                        scope,
                        f"skipped {skip.length} garbage byte(s) before the FIT header",
                        byte_offset=skip.offset,
                        data={"length": skip.length},
                    )
                )
            else:
                resync_count += 1
                provenance.append(
                    ProvenanceEntry(
                        "RESYNC_SKIPPED_BYTES",
                        "repaired",
                        scope,
                        f"skipped {skip.length} undecodable byte(s) after {skip.reason}"
                        f" at offset {skip.offset}; decoding resumed",
                        byte_offset=skip.offset,
                        data={"length": skip.length, "defect_code": skip.reason},
                    )
                )
        for defect in stream_defects:
            if defect.offset in skip_offsets and defect.severity == "structural":
                continue  # resynchronized: the SkippedBytes provenance tells the story
            if defect.severity == "fatal":
                errors.append(defect_to_error(defect, suggestion=_SUGGESTIONS.get(defect.code)))
            elif defect.code in _CONTINUE_CODES:
                warnings.append(Diagnostic(defect.code, defect.detail, f"byte {defect.offset}"))
            else:
                # Structural defect that stopped the stream: prefix salvage (F5 → resync).
                recovery_engaged = True
                code = (
                    "TRUNCATED_TAIL_SALVAGED"
                    if defect.code == "FIT_TRUNCATED"
                    else "STREAM_STOPPED_AT_DEFECT"
                )
                provenance.append(
                    ProvenanceEntry(
                        code,
                        "repaired",
                        scope,
                        f"{defect.detail}; salvaged {len(messages)} complete message(s)",
                        byte_offset=defect.offset,
                        data={"defect_code": defect.code},
                    )
                )
                if (
                    defect.code == "FIT_TRUNCATED"
                    and header is not None
                    and header.data_size
                    and body_bytes_decoded > 0
                ):
                    est_total = round(len(messages) * header.data_size / body_bytes_decoded)

        if messages or header is not None:
            part = _build_part(messages)
            if strip_pii:
                _strip_pii(part, provenance, scope)
            if not include_unknown:
                _drop_unknown(part, provenance, scope)
            if part.file_type == "activity":
                part.activity = build_activity(
                    part.messages,
                    warnings,
                    provenance,
                    scope,
                    skipped_ranges=[(sk.offset, sk.offset + sk.length) for sk in skips],
                    forensic=(mode == "forensic"),
                )
            parts.append(part)
            total_recovered += len(messages)

        part_index += 1
        if consumed <= offset:
            break
        offset = consumed
        if offset >= len(data):
            break
        if not _looks_like_header(data, offset):
            junk = Defect(
                "FIT_TRAILING_JUNK",
                f"{len(data) - offset} byte(s) after the final CRC are not a chained FIT file",
                offset,
                "structural",
            )
            if mode == "strict":
                raise defect_to_error(junk)
            if not any(
                d.severity == "structural" and d.code not in _CONTINUE_CODES for d in stream_defects
            ):
                warnings.append(Diagnostic(junk.code, junk.detail, f"byte {offset}"))
            break

    ok = any(p.messages for p in parts) and not any(
        e.code in ("FIT_EMPTY", "FIT_TOO_SMALL", "NOT_FIT_FORMAT") for e in errors
    )
    if not ok and not errors:
        # Contract #5: ok=false must always be explained. The valid-but-empty
        # shell (taxonomy #16, seen in the wild as 16-byte tool output).
        errors.append(
            FitError(
                "FIT_NO_CONTENT",
                "structurally valid FIT container with no messages — the data is"
                " genuinely absent, not recoverable",
                suggestion="nothing to salvage; check the device/app that wrote it",
            )
        )
    recovery = (
        RecoveryReport(
            recovered_records=total_recovered,
            estimated_total_records=est_total,
            bytes_read=len(data),
            bytes_skipped=total_skipped,
            resync_count=resync_count,
        )
        if recovery_engaged
        else None
    )
    return ParseResult(
        ok=ok,
        mode=mode,
        source=source,
        parts=parts,
        provenance=provenance,
        warnings=warnings,
        errors=errors,
        recovery=recovery,
        include_raw=include_raw,
    )


def _build_part(messages: list[Message]) -> FitPart:
    file_id: dict[str, Any] | None = None
    file_type = "unknown"
    for m in messages:
        if m.global_num == 0:
            file_id = {k: fv.value for k, fv in m.fields.items()}
            t = m.get("type")
            if isinstance(t, str):
                file_type = t
            elif t is not None:
                file_type = f"unknown_{t}"
            break
    return FitPart(file_type=file_type, file_id=file_id, messages=messages)


def _strip_pii(part: FitPart, provenance: list[ProvenanceEntry], scope: str) -> None:
    removed_msgs = 0
    nulled_fields = 0
    kept: list[Message] = []
    for m in part.messages:
        if m.name in _PII_MESSAGES:
            removed_msgs += 1
            continue
        if any(f in m.fields for f in _PII_FIELDS):
            fields = dict(m.fields)
            for f in _PII_FIELDS:
                if f in fields:
                    fields[f] = FieldValue(None, None, fields[f].units)
                    nulled_fields += 1
            m = dataclasses.replace(m, fields=fields)
        kept.append(m)
    part.messages = kept
    if part.file_id and "serial_number" in part.file_id:
        part.file_id["serial_number"] = None
    if removed_msgs or nulled_fields:
        provenance.append(
            ProvenanceEntry(
                "PII_STRIPPED",
                "dropped",
                scope,
                f"removed {removed_msgs} PII message(s), nulled {nulled_fields}"
                f" serial-number field(s) (strip_pii=True)",
                data={"messages_removed": removed_msgs, "fields_nulled": nulled_fields},
            )
        )


def _drop_unknown(part: FitPart, provenance: list[ProvenanceEntry], scope: str) -> None:
    known = [m for m in part.messages if not m.name.startswith("unknown_")]
    dropped = len(part.messages) - len(known)
    part.messages = known
    if dropped:
        provenance.append(
            ProvenanceEntry(
                "UNKNOWN_MESSAGES_OMITTED",
                "ignored",
                scope,
                f"{dropped} unknown message(s) omitted from output (include_unknown=False)",
                data={"count": dropped},
            )
        )
