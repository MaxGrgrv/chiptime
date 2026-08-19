"""Intake: container unwrapping and content sniffing (taxonomy #14, #15).

Runs before frame decoding. Never raises; returns typed defects (ADR-0003).
"""

from __future__ import annotations

import gzip
import io
import zipfile
from dataclasses import dataclass, field

from chiptime.errors import Defect, ProvenanceEntry

MAX_UNWRAP_DEPTH = 3

GZIP_MAGIC = b"\x1f\x8b"
ZIP_MAGIC = b"PK\x03\x04"


@dataclass
class IntakeResult:
    data: bytes
    unwrapped: tuple[str, ...] = ()
    defects: list[Defect] = field(default_factory=list)
    provenance: list[ProvenanceEntry] = field(default_factory=list)


def unwrap(data: bytes) -> IntakeResult:
    """Peel containers, then sniff for non-FIT content."""
    result = IntakeResult(data)
    for _ in range(MAX_UNWRAP_DEPTH):
        if result.data.startswith(GZIP_MAGIC):
            try:
                result.data = gzip.decompress(result.data)
            except OSError as exc:
                result.defects.append(
                    Defect(
                        "NOT_FIT_FORMAT", f"gzip container failed to decompress: {exc}", 0, "fatal"
                    )
                )
                return result
            result.unwrapped = (*result.unwrapped, "gzip")
            continue
        if result.data.startswith(ZIP_MAGIC):
            if not _unzip(result):
                return result
            continue
        break

    if _fit_plausible(result.data):
        return result
    looks = _sniff(result.data)
    if looks is not None:
        result.defects.append(Defect("NOT_FIT_FORMAT", f"content is {looks}", 0, "fatal"))
    # Unrecognized bytes fall through to the frame reader — its defects
    # (FIT_EMPTY / FIT_TOO_SMALL / NOT_FIT_FORMAT) are more precise than a guess.
    return result


def _unzip(result: IntakeResult) -> bool:
    try:
        zf = zipfile.ZipFile(io.BytesIO(result.data))
        names = [n for n in zf.namelist() if n.lower().endswith(".fit")]
        if not names:
            result.defects.append(
                Defect("NOT_FIT_FORMAT", "zip archive contains no .fit entries", 0, "fatal")
            )
            return False
        names.sort()
        blobs = [zf.read(n) for n in names]
    except (zipfile.BadZipFile, NotImplementedError, OSError) as exc:
        result.defects.append(
            Defect("NOT_FIT_FORMAT", f"zip container failed to read: {exc}", 0, "fatal")
        )
        return False
    result.data = b"".join(blobs)
    result.unwrapped = (*result.unwrapped, "zip")
    if len(blobs) > 1:
        # Multiple .fit entries become the legal chained form (taxonomy #12).
        result.provenance.append(
            ProvenanceEntry(
                "ZIP_ENTRIES_CHAINED",
                "reinterpreted",
                "intake",
                f"{len(blobs)} .fit entries from the zip parsed as chained parts",
                data={"entries": names},
            )
        )
    return True


def _fit_plausible(data: bytes) -> bool:
    """Cheap positive check: plausible header-size byte or the .FIT magic."""
    if len(data) < 12:
        return True  # let the frame reader report precisely (FIT_EMPTY/TOO_SMALL)
    return data[8:12] == b".FIT" or data[0] in (12, 14)


def _sniff(data: bytes) -> str | None:
    head = data[:512].lstrip(b"\xef\xbb\xbf \t\r\n")
    lower = head.lower()
    if head.startswith(b"<"):
        if b"<gpx" in lower:
            return "GPX (XML with <gpx> root)"
        if b"<trainingcenterdatabase" in lower:
            return "TCX (XML with <TrainingCenterDatabase> root)"
        if b"<!doctype html" in lower or b"<html" in lower:
            return "an HTML page (likely a failed-download error page)"
        return "XML (neither GPX nor TCX)"
    if head.startswith((b"{", b"[")):
        return "JSON"
    sample = head[:256]
    if sample and all(0x09 <= b <= 0x7E or b in (0x0A, 0x0D) for b in sample):
        return "plain text"
    return None
