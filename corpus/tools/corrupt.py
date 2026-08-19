#!/usr/bin/env python3
"""Deterministic corruption + wrapping operations for corpus generation.

Every op is a pure function bytes -> bytes with explicit parameters —
no randomness, no wall clock (zip/gzip use fixed timestamps). Ops are
addressed by name from case.json build pipelines (see gen_all.py).
"""

from __future__ import annotations

import gzip
import io
import struct
import zipfile


def truncate(b: bytes, *, at: int) -> bytes:
    return b[:at]


def flip_bit(b: bytes, *, offset: int, bit: int) -> bytes:
    out = bytearray(b)
    out[offset] ^= 1 << bit
    return bytes(out)


def overwrite(b: bytes, *, offset: int, data: str) -> bytes:
    raw = bytes.fromhex(data)
    out = bytearray(b)
    out[offset : offset + len(raw)] = raw
    return bytes(out)


def insert(
    b: bytes, *, offset: int, data: str = "", repeat_byte: int | None = None, count: int = 0
) -> bytes:
    raw = bytes([repeat_byte]) * count if repeat_byte is not None else bytes.fromhex(data)
    return b[:offset] + raw + b[offset:]


def delete(b: bytes, *, offset: int, length: int) -> bytes:
    return b[:offset] + b[offset + length :]


def append(b: bytes, *, data: str = "", repeat_byte: int | None = None, count: int = 0) -> bytes:
    raw = bytes([repeat_byte]) * count if repeat_byte is not None else bytes.fromhex(data)
    return b + raw


def set_data_size(b: bytes, *, value: int) -> bytes:
    """Lie in the header's data_size field (offset 4, LE u32)."""
    return b[:4] + struct.pack("<I", value) + b[8:]


def break_file_crc(b: bytes) -> bytes:
    return b[:-2] + struct.pack("<H", struct.unpack("<H", b[-2:])[0] ^ 0x5555)


def fix_file_crc(b: bytes) -> bytes:
    """Recompute the trailing file CRC after header surgery (device-consistent)."""
    from build_fit import crc16  # same tools dir

    return b[:-2] + struct.pack("<H", crc16(b[:-2]))


def fix_header_crc(b: bytes) -> bytes:
    """Recompute the 14-byte header's CRC after header surgery."""
    from build_fit import crc16

    return b[:12] + struct.pack("<H", crc16(b[:12])) + b[14:]


def zero_file_crc(b: bytes) -> bytes:
    return b[:-2] + b"\x00\x00"


def strip_file_crc(b: bytes) -> bytes:
    return b[:-2]


def chain(b: bytes, *, seeds: list[bytes]) -> bytes:
    out = b
    for extra in seeds:
        out += extra
    return out


def gzip_wrap(b: bytes) -> bytes:
    return gzip.compress(b, mtime=0)


def zip_wrap(b: bytes, *, name: str = "activity.fit") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        z.writestr(info, b)
    return buf.getvalue()


# ── non-FIT payloads (taxonomy #15) ─────────────────────────────────────────

GPX = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<gpx version="1.1" creator="chiptime-corpus"><trk><name>oops</name>'
    b'<trkseg><trkpt lat="52.37" lon="4.89"><ele>10</ele></trkpt></trkseg></trk></gpx>\n'
)
TCX = (
    b'<?xml version="1.0" encoding="UTF-8"?>\n'
    b'<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">'
    b"<Activities/></TrainingCenterDatabase>\n"
)
HTML = (
    b"<!DOCTYPE html>\n<html><head><title>500</title></head><body>download failed</body></html>\n"
)
JSON_PAYLOAD = b'{"error": "this is not a fit file"}\n'


def payload(kind: str) -> bytes:
    return {
        "gpx": GPX,
        "tcx": TCX,
        "html": HTML,
        "json": JSON_PAYLOAD,
        "empty": b"",
        "tiny": b"\x0c",
    }[kind]
