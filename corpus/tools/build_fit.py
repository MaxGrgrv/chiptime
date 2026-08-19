#!/usr/bin/env python3
"""Deterministic synthetic FIT builder for corpus fixtures.

Self-contained BY DESIGN (ADR-0001 §3): this writer must never import chiptime.
If the parser and the fixture generator shared tables, a shared bug would make
corpus cases pass while both are wrong. Wire facts here are cross-checked
against independent implementations in F3 (see docs/features/f03-*).

No randomness, no wall clock: identical calls produce identical bytes.
"""

from __future__ import annotations

import struct
from datetime import UTC, datetime

FIT_EPOCH_UNIX = 631065600  # 1989-12-31T00:00:00Z

CRC_TABLE = [
    0x0000,
    0xCC01,
    0xD801,
    0x1400,
    0xF001,
    0x3C00,
    0x2800,
    0xE401,
    0xA001,
    0x6C00,
    0x7800,
    0xB401,
    0x5000,
    0x9C01,
    0x8801,
    0x4400,
]


def crc16(data: bytes, crc: int = 0) -> int:
    for byte in data:
        tmp = CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ CRC_TABLE[byte & 0xF]
        tmp = CRC_TABLE[crc & 0xF]
        crc = (crc >> 4) & 0x0FFF
        crc = crc ^ tmp ^ CRC_TABLE[(byte >> 4) & 0xF]
    return crc


# name -> (base type byte, struct code, size). string/byte handled specially.
BASE_TYPES = {
    "enum": (0x00, "B", 1),
    "sint8": (0x01, "b", 1),
    "uint8": (0x02, "B", 1),
    "sint16": (0x83, "h", 2),
    "uint16": (0x84, "H", 2),
    "sint32": (0x85, "i", 4),
    "uint32": (0x86, "I", 4),
    "string": (0x07, None, 1),
    "float32": (0x88, "f", 4),
    "float64": (0x89, "d", 8),
    "uint8z": (0x0A, "B", 1),
    "uint16z": (0x8B, "H", 2),
    "uint32z": (0x8C, "I", 4),
    "byte": (0x0D, None, 1),
    "sint64": (0x8E, "q", 8),
    "uint64": (0x8F, "Q", 8),
    "uint64z": (0x90, "Q", 8),
}

# Sentinel ("invalid") values per base type, used to fill absent values.
INVALID = {
    "enum": 0xFF,
    "sint8": 0x7F,
    "uint8": 0xFF,
    "sint16": 0x7FFF,
    "uint16": 0xFFFF,
    "sint32": 0x7FFFFFFF,
    "uint32": 0xFFFFFFFF,
    "uint8z": 0,
    "uint16z": 0,
    "uint32z": 0,
    "sint64": 0x7FFFFFFFFFFFFFFF,
    "uint64": 0xFFFFFFFFFFFFFFFF,
    "uint64z": 0,
}


def fit_ts(dt: datetime) -> int:
    return int(dt.timestamp()) - FIT_EPOCH_UNIX


def semicircles(deg: float) -> int:
    return round(deg * (2**31) / 180.0)


class FitBuilder:
    """Low-level record-by-record FIT stream writer."""

    def __init__(self, protocol: int = 0x20, profile: int = 21141, header_size: int = 14):
        self.protocol = protocol
        self.profile = profile
        self.header_size = header_size
        self.body = bytearray()
        # local id -> list of (field_num, type_name, count)
        self._defs: dict[int, list[tuple[int, str, int]]] = {}

    def define(
        self,
        local: int,
        global_num: int,
        fields: list[tuple[int, str, int]],
        *,
        big_endian: bool = False,
        dev_fields: list[tuple[int, int, int]] | None = None,  # (field_num, size, dev_idx)
    ) -> None:
        header = 0x40 | (0x20 if dev_fields else 0x00) | (local & 0x0F)
        arch = 1 if big_endian else 0
        out = bytearray([header, 0, arch])
        out += struct.pack(">H" if big_endian else "<H", global_num)
        out.append(len(fields))
        for num, tname, count in fields:
            code, _, size = BASE_TYPES[tname]
            out += bytes([num, size * count, code])
        if dev_fields:
            out.append(len(dev_fields))
            for num, size, dev_idx in dev_fields:
                out += bytes([num, size, dev_idx])
        self.body += out
        self._defs[local] = list(fields)
        self._arch = getattr(self, "_arch", {})
        self._arch[local] = big_endian
        self._devs = getattr(self, "_devs", {})
        self._devs[local] = list(dev_fields or [])

    def data(self, local: int, *values: object, dev_values: list[bytes] | None = None) -> None:
        self.body += bytes([local & 0x0F])
        self._payload(local, values, dev_values)

    def data_compressed(self, local: int, time_offset: int, *values: object) -> None:
        """Compressed-timestamp header: local in 0..3, offset in 0..31."""
        self.body += bytes([0x80 | ((local & 0x03) << 5) | (time_offset & 0x1F)])
        self._payload(local, values, None)

    def _payload(
        self, local: int, values: tuple[object, ...], dev_values: list[bytes] | None
    ) -> None:
        fields = self._defs[local]
        big = self._arch.get(local, False)
        end = ">" if big else "<"
        for (_num, tname, count), value in zip(fields, values, strict=True):
            code_info = BASE_TYPES[tname]
            if tname == "string":
                if isinstance(value, bytes) and len(value) == count:
                    raw = value  # verbatim: lets fixtures write unterminated strings (#33)
                else:
                    raw = value.encode("utf-8") if isinstance(value, str) else bytes(value)  # type: ignore[arg-type]
                    if len(raw) >= count:
                        raw = raw[: count - 1] + b"\x00"
                    else:
                        raw = raw + b"\x00" * (count - len(raw))
                self.body += raw
            elif tname == "byte":
                raw = bytes(value)  # type: ignore[arg-type]
                assert len(raw) == count
                self.body += raw
            else:
                _, sc, _size = code_info
                vals = value if isinstance(value, (list, tuple)) else [value]
                assert len(vals) == count
                for v in vals:
                    if v is None and tname in ("float32", "float64"):
                        self.body += b"\xff" * _size
                        continue
                    v2 = INVALID[tname] if v is None else v
                    self.body += struct.pack(end + sc, v2)  # type: ignore[operator]
        devs = self._devs.get(local, [])
        dev_values = dev_values or []
        for (_n, size, _i), raw in zip(devs, dev_values, strict=True):
            assert len(raw) == size
            self.body += raw

    def raw(self, b: bytes) -> None:
        self.body += b

    def build(
        self,
        *,
        data_size: int | str = "auto",
        header_crc: str = "good",  # good | zero | bad  (12-byte headers have none)
        file_crc: str = "good",  # good | bad | omit | zero
    ) -> bytes:
        size = len(self.body) if data_size == "auto" else int(data_size)
        head = bytearray([self.header_size, self.protocol])
        head += struct.pack("<H", self.profile)
        head += struct.pack("<I", size)
        head += b".FIT"
        if self.header_size >= 14:
            if header_crc == "zero":
                head += struct.pack("<H", 0)
            else:
                crc = crc16(bytes(head[:12]))
                if header_crc == "bad":
                    crc ^= 0x5555
                head += struct.pack("<H", crc)
        out = bytes(head) + bytes(self.body)
        if file_crc == "omit":
            return out
        crc = crc16(out)
        if file_crc == "bad":
            crc ^= 0x5555
        if file_crc == "zero":
            crc = 0
        return out + struct.pack("<H", crc)


# ── message/field constants used by seeds (globals per FIT profile) ──────────

FILE_ID = 0
SESSION = 18
LAP = 19
RECORD = 20
EVENT = 21
DEVICE_INFO = 23
ACTIVITY = 34
FIELD_DESCRIPTION = 206
DEVELOPER_DATA_ID = 207
HRV = 78

T0 = datetime(2026, 6, 1, 9, 0, 0, tzinfo=UTC)

RECORD_FIELDS_FULL = [
    (253, "uint32", 1),  # timestamp
    (0, "sint32", 1),  # position_lat (semicircles)
    (1, "sint32", 1),  # position_long
    (2, "uint16", 1),  # altitude ( /5 - 500 m)
    (3, "uint8", 1),  # heart_rate (bpm)
    (4, "uint8", 1),  # cadence (rpm)
    (5, "uint32", 1),  # distance ( /100 m)
    (6, "uint16", 1),  # speed ( /1000 m/s)
    (7, "uint16", 1),  # power (W)
    (13, "sint8", 1),  # temperature (C)
]
RECORD_FIELDS_NO_POWER = [f for f in RECORD_FIELDS_FULL if f[0] != 7]


def _ride_records(b: FitBuilder, n: int, t0: int) -> None:
    """1 Hz cycling records: ramps and square waves, integer-deterministic."""
    b.define(1, RECORD, RECORD_FIELDS_FULL)
    b.define(2, RECORD, RECORD_FIELDS_NO_POWER)
    lat0, lon0 = semicircles(52.370000), semicircles(4.890000)
    dist = 0
    for i in range(n):
        if i == n // 2:
            # Devices periodically re-emit definitions; also gives resync an anchor.
            b.define(1, RECORD, RECORD_FIELDS_FULL)
        ts = t0 + i
        lat = lat0 + i * 120  # ~ heading north
        lon = lon0 + i * 40
        alt_m = 10 + (i if i <= n // 2 else n - i)  # triangle
        alt = (alt_m + 500) * 5
        hr = 120 + (i * 40) // max(n - 1, 1)
        cad = 85
        speed = 8333  # 8.333 m/s
        dist += 833  # +8.33 m
        power: int | None = 180 if (i // 10) % 2 == 0 else 220
        if 30 <= i < 35:
            power = 0  # coasting — REAL zero (taxonomy #64)
        temp = 21
        if 50 <= i < 56:  # power meter dropout: field absent entirely (#68)
            b.data(2, ts, lat, lon, alt, hr, cad, dist, speed, temp)
        else:
            b.data(1, ts, lat, lon, alt, hr, cad, dist, speed, power, temp)


def ride_smooth(n: int = 120) -> bytes:
    """Clean 2-minute cycling activity: the primary seed."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(
        0,
        FILE_ID,
        [(0, "enum", 1), (1, "uint16", 1), (2, "uint16", 1), (3, "uint32z", 1), (4, "uint32", 1)],
    )
    b.data(0, 4, 1, 3121, 1234567, t0)  # type=activity, manufacturer=garmin
    b.define(
        3,
        DEVICE_INFO,
        [
            (253, "uint32", 1),
            (0, "uint8", 1),
            (2, "uint16", 1),
            (4, "uint16", 1),
            (3, "uint32z", 1),
        ],
    )
    b.data(3, t0, 0, 1, 3121, 1234567)
    b.define(
        4,
        EVENT,
        [(253, "uint32", 1), (0, "enum", 1), (1, "enum", 1), (3, "uint32", 1), (4, "uint8", 1)],
    )
    b.data(4, t0, 0, 0, 0, 0)  # event=timer, type=start, data=manual(0)
    _ride_records(b, n, t0)
    b.data(4, t0 + n, 0, 4, 0, 0)  # timer stop_all
    dist = 833 * n
    b.define(
        5,
        LAP,
        [
            (253, "uint32", 1),
            (254, "uint16", 1),
            (0, "enum", 1),
            (1, "enum", 1),
            (2, "uint32", 1),
            (7, "uint32", 1),
            (8, "uint32", 1),
            (9, "uint32", 1),
        ],
    )
    b.data(5, t0 + n, 0, 9, 1, t0, n * 1000, n * 1000, dist)  # event=lap(9), type=stop(1)
    b.define(
        6,
        SESSION,
        [
            (253, "uint32", 1),
            (254, "uint16", 1),
            (0, "enum", 1),
            (1, "enum", 1),
            (2, "uint32", 1),
            (5, "enum", 1),
            (6, "enum", 1),
            (7, "uint32", 1),
            (8, "uint32", 1),
            (9, "uint32", 1),
            (16, "uint8", 1),
            (17, "uint8", 1),
            (25, "uint16", 1),
            (26, "uint16", 1),
        ],
    )
    b.data(6, t0 + n, 0, 8, 1, t0, 2, 0, n * 1000, n * 1000, dist, 140, 160, 0, 1)
    b.define(
        7,
        ACTIVITY,
        [
            (253, "uint32", 1),
            (0, "uint32", 1),
            (1, "uint16", 1),
            (2, "enum", 1),
            (3, "enum", 1),
            (4, "enum", 1),
            (5, "uint32", 1),
        ],
    )
    b.data(7, t0 + n, n * 1000, 1, 0, 26, 1, t0 + n + 7200)  # local = UTC+2
    return b.build()


def run_basic(n: int = 60) -> bytes:
    """Clean 1-minute run, no power, running cadence."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(
        0,
        FILE_ID,
        [(0, "enum", 1), (1, "uint16", 1), (2, "uint16", 1), (3, "uint32z", 1), (4, "uint32", 1)],
    )
    b.data(0, 4, 1, 4315, 7654321, t0)
    b.define(
        4,
        EVENT,
        [(253, "uint32", 1), (0, "enum", 1), (1, "enum", 1), (3, "uint32", 1), (4, "uint8", 1)],
    )
    b.data(4, t0, 0, 0, 0, 0)
    b.define(1, RECORD, RECORD_FIELDS_NO_POWER)
    lat0, lon0 = semicircles(41.385000), semicircles(2.170000)
    dist = 0
    for i in range(n):
        alt = (12 + 500) * 5
        hr = 130 + (i * 30) // max(n - 1, 1)
        dist += 300  # 3 m/s
        b.data(1, t0 + i, lat0 + i * 60, lon0 + i * 20, alt, hr, 87, dist, 3000, 18)
    b.data(4, t0 + n, 0, 4, 0, 0)
    b.define(
        6,
        SESSION,
        [
            (253, "uint32", 1),
            (254, "uint16", 1),
            (0, "enum", 1),
            (1, "enum", 1),
            (2, "uint32", 1),
            (5, "enum", 1),
            (6, "enum", 1),
            (7, "uint32", 1),
            (8, "uint32", 1),
            (9, "uint32", 1),
            (16, "uint8", 1),
            (17, "uint8", 1),
            (25, "uint16", 1),
            (26, "uint16", 1),
        ],
    )
    b.data(6, t0 + n, 0, 8, 1, t0, 1, 0, n * 1000, n * 1000, dist, 145, 160, 0, 0)
    b.define(
        7,
        ACTIVITY,
        [
            (253, "uint32", 1),
            (0, "uint32", 1),
            (1, "uint16", 1),
            (2, "enum", 1),
            (3, "enum", 1),
            (4, "enum", 1),
            (5, "uint32", 1),
        ],
    )
    b.data(7, t0 + n, n * 1000, 1, 0, 26, 1, t0 + n + 3600)
    return b.build()


def redefinition_stress() -> bytes:
    """Local 0 remapped between record/event repeatedly (taxonomy #20)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (4, "uint32", 1)])
    b.data(0, 4, t0)
    for i in range(6):
        if i % 2 == 0:
            b.define(0, RECORD, [(253, "uint32", 1), (7, "uint16", 1)])
            b.data(0, t0 + i, 200 + i)
        else:
            b.define(0, EVENT, [(253, "uint32", 1), (0, "enum", 1), (1, "enum", 1)])
            b.data(0, t0 + i, 0, 0)
    return b.build()


def compressed_ts() -> bytes:
    """Compressed timestamp headers incl. a 32 s rollover (taxonomy #21)."""
    b = FitBuilder()
    anchor = (fit_ts(T0) & ~0x1F) | 28
    b.define(0, FILE_ID, [(0, "enum", 1), (4, "uint32", 1)])
    b.data(0, 4, anchor - 100)
    b.define(2, RECORD, [(253, "uint32", 1), (3, "uint8", 1)])
    b.data(2, anchor, 120)
    b.define(1, RECORD, [(3, "uint8", 1)])
    b.data_compressed(1, 29, 121)
    b.data_compressed(1, 30, 122)
    b.data_compressed(1, 2, 123)  # rollover
    return b.build()


def sentinel_soup() -> bytes:
    """Sentinel invalids across base types (taxonomy #26)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (3, "uint32z", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, None, t0)
    b.define(1, RECORD, RECORD_FIELDS_FULL)
    b.data(1, t0, None, None, None, None, 85, 100, 8333, None, None)
    b.data(
        1,
        t0 + 1,
        semicircles(52.37),
        semicircles(4.89),
        (12 + 500) * 5,
        130,
        85,
        933,
        8333,
        210,
        21,
    )
    return b.build()


def big_endian_mixed() -> bytes:
    """Big-endian record definition alongside little-endian ones (taxonomy #32)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (4, "uint32", 1)])
    b.data(0, 4, t0)
    b.define(1, RECORD, [(253, "uint32", 1), (7, "uint16", 1), (13, "sint8", 1)], big_endian=True)
    for i in range(3):
        b.data(1, t0 + i, 200 + i, -4)
    return b.build()


def string_edges() -> bytes:
    """Strings: clean, unterminated, invalid UTF-8 (taxonomy #33)."""
    b = FitBuilder()
    b.define(0, FILE_ID, [(0, "enum", 1), (8, "string", 8)])
    b.data(0, 4, "Edge")
    b.define(1, DEVICE_INFO, [(27, "string", 4)])
    b.data(1, b"abcd")
    b.define(2, DEVICE_INFO, [(27, "string", 6)])
    b.data(2, b"ab\xffc\x00\x00")
    return b.build()


def hrv_arrays() -> bytes:
    """HRV time arrays with sentinel-padded tails (taxonomy #34)."""
    b = FitBuilder()
    b.define(0, FILE_ID, [(0, "enum", 1)])
    b.data(0, 4)
    b.define(1, HRV, [(0, "uint16", 5)])
    b.data(1, [500, 520, 530, None, None])
    b.data(1, [510, None, 540, None, None])  # interior None preserved, tail trimmed
    return b.build()


def float_fields() -> bytes:
    """NaN/Inf floats that must null with a diagnostic (taxonomy #35)."""
    b = FitBuilder()
    b.define(0, FILE_ID, [(0, "enum", 1)])
    b.data(0, 4)
    b.define(1, 4242, [(0, "float32", 1), (1, "float64", 1), (2, "float32", 1)])
    b.data(1, float("nan"), float("inf"), 1.5)
    return b.build()


def uint64_fields() -> bytes:
    """64-bit integers beyond JSON-safe range (taxonomy #35)."""
    b = FitBuilder()
    b.define(0, FILE_ID, [(0, "enum", 1)])
    b.data(0, 4)
    b.define(1, 4242, [(0, "uint16", 1), (1, "uint64", 1), (2, "uint64z", 1), (3, "sint64", 1)])
    b.data(1, 55, 2**60, None, -5)
    return b.build()


def invalid_base_type() -> bytes:
    """A definition declaring bogus base type 0x7B for one field (taxonomy #25)."""
    b = FitBuilder()
    b.define(0, FILE_ID, [(0, "enum", 1)])
    b.data(0, 4)
    b.raw(bytes([0x41, 0, 0]) + struct.pack("<H", RECORD) + bytes([2, 253, 4, 0x86, 7, 2, 0x7B]))
    b.raw(bytes([0x01]) + struct.pack("<I", fit_ts(T0)) + b"\xde\xad")
    return b.build()


def undefined_local() -> bytes:
    """A data byte for a never-defined local type mid-stream, junk after it,
    then a fresh definition — data on BOTH sides must survive (taxonomy #19)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (4, "uint32", 1)])
    b.data(0, 4, t0)
    b.define(1, RECORD, [(253, "uint32", 1), (3, "uint8", 1), (7, "uint16", 1)])
    for i in range(3):
        b.data(1, t0 + i, 120 + i, 200)
    b.raw(bytes([0x07]) + b"\xba\xdb\xad\xba\xdb\xad\xba\xdb\xad\xba")
    b.define(2, RECORD, [(253, "uint32", 1), (3, "uint8", 1), (7, "uint16", 1)])
    for i in range(3, 6):
        b.data(2, t0 + i, 120 + i, 205)
    return b.build()


def frame_shift() -> bytes:
    """One inserted byte misaligns every subsequent frame until the next
    definition re-anchors decoding (taxonomy #11)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (4, "uint32", 1)])
    b.data(0, 4, t0)
    b.define(1, RECORD, [(253, "uint32", 1), (7, "uint16", 1)])
    for i in range(4):
        b.data(1, t0 + i, 200)
    b.raw(b"\x00")  # the shift: swallowed as a bogus local-0 data frame
    for i in range(4, 8):
        b.data(1, t0 + i, 200)
    b.define(2, RECORD, [(253, "uint32", 1), (7, "uint16", 1)])
    for i in range(8, 10):
        b.data(2, t0 + i, 210)
    return b.build()


def course_file() -> bytes:
    """A FIT course file (taxonomy #80: not an activity, still parses)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 6, 1, t0)  # type=course
    b.define(1, 31, [(4, "enum", 1), (5, "string", 12)])  # course: sport, name
    b.data(1, 2, "Loop 40k")
    b.define(2, RECORD, [(0, "sint32", 1), (1, "sint32", 1), (5, "uint32", 1)])
    for i in range(5):
        b.data(2, semicircles(52.37) + i * 1000, semicircles(4.89) + i * 400, i * 100000)
    return b.build()


def workout_file() -> bytes:
    """A FIT workout file (taxonomy #80)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 5, 1, t0)  # type=workout
    b.define(1, 26, [(4, "enum", 1), (6, "uint16", 1), (8, "string", 10)])
    b.data(1, 2, 4, "4x8 VO2")
    return b.build()


def monitoring_file() -> bytes:
    """A monitoring file: unknown content must decode-don't-crash (taxonomy #80/#82)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 15, 1, t0)  # type=monitoring_a
    b.define(1, 55, [(253, "uint32", 1), (0, "uint32", 1), (1, "uint16", 1)])  # monitoring
    for i in range(3):
        b.data(1, t0 + i * 60, 1000 + i * 500, 60 + i)
    return b.build()


def summary_only() -> bytes:
    """Manual/summary-only activity: session, zero records (taxonomy #79)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(
        6,
        SESSION,
        [
            (253, "uint32", 1),
            (254, "uint16", 1),
            (0, "enum", 1),
            (1, "enum", 1),
            (2, "uint32", 1),
            (5, "enum", 1),
            (6, "enum", 1),
            (7, "uint32", 1),
            (8, "uint32", 1),
            (9, "uint32", 1),
        ],
    )
    b.data(6, t0 + 3600, 0, 8, 1, t0, 1, 0, 3600000, 3600000, 1000000)
    b.define(
        7,
        ACTIVITY,
        [
            (253, "uint32", 1),
            (0, "uint32", 1),
            (1, "uint16", 1),
            (2, "enum", 1),
            (3, "enum", 1),
            (4, "enum", 1),
        ],
    )
    b.data(7, t0 + 3600, 3600000, 1, 0, 26, 1)
    return b.build()


def _dev_header(b: FitBuilder, t0: int) -> None:
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)


def dev_fields_stryd() -> bytes:
    """Known-vendor developer fields: Stryd power + LSS (taxonomy #22d)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    _dev_header(b, t0)
    b.define(1, DEVELOPER_DATA_ID, [(1, "byte", 16), (2, "uint16", 1), (3, "uint8", 1)])
    b.data(1, bytes(range(16)), 95, 0)  # application_id, manufacturer=stryd, index 0
    b.define(
        2,
        FIELD_DESCRIPTION,
        [
            (0, "uint8", 1),
            (1, "uint8", 1),
            (2, "uint8", 1),
            (3, "string", 24),
            (6, "uint8", 1),
            (8, "string", 8),
        ],
    )
    b.data(2, 0, 5, 0x84, "Power", 0, "Watts")
    b.data(2, 0, 6, 0x84, "Leg Spring Stiffness", 10, "kN/m")
    b.define(3, RECORD, [(253, "uint32", 1), (3, "uint8", 1)], dev_fields=[(5, 2, 0), (6, 2, 0)])
    for i in range(4):
        b.data(3, t0 + i, 140 + i, dev_values=[struct.pack("<H", 250 + i), struct.pack("<H", 103)])
    return b.build()


def dev_missing_description() -> bytes:
    """developer_data_id present, field_description missing (taxonomy #22a)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    _dev_header(b, t0)
    b.define(1, DEVELOPER_DATA_ID, [(1, "byte", 16), (2, "uint16", 1), (3, "uint8", 1)])
    b.data(1, bytes(range(16)), 255, 0)  # manufacturer=development
    b.define(3, RECORD, [(253, "uint32", 1), (3, "uint8", 1)], dev_fields=[(5, 2, 0)])
    for i in range(3):
        b.data(3, t0 + i, 140 + i, dev_values=[struct.pack("<H", 300 + i)])
    return b.build()


def dev_no_data_id() -> bytes:
    """field_description without developer_data_id (fitparse #124 class)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    _dev_header(b, t0)
    b.define(
        2,
        FIELD_DESCRIPTION,
        [(0, "uint8", 1), (1, "uint8", 1), (2, "uint8", 1), (3, "string", 16), (8, "string", 8)],
    )
    b.data(2, 0, 9, 0x02, "SmO2ish", "%")
    b.define(3, RECORD, [(253, "uint32", 1)], dev_fields=[(9, 1, 0)])
    for i in range(3):
        b.data(3, t0 + i, dev_values=[bytes([60 + i])])
    return b.build()


def dev_null_name() -> bytes:
    """field_description with an empty name (RunScribe / fitparse #62 class)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    _dev_header(b, t0)
    b.define(1, DEVELOPER_DATA_ID, [(1, "byte", 16), (2, "uint16", 1), (3, "uint8", 1)])
    b.data(1, bytes(reversed(range(16))), 255, 0)
    b.define(
        2, FIELD_DESCRIPTION, [(0, "uint8", 1), (1, "uint8", 1), (2, "uint8", 1), (3, "string", 8)]
    )
    b.data(2, 0, 7, 0x84, "")  # null name
    b.define(3, RECORD, [(253, "uint32", 1)], dev_fields=[(7, 2, 0)])
    b.data(3, t0, dev_values=[struct.pack("<H", 777)])
    return b.build()


def dev_late_description() -> bytes:
    """field_description arrives AFTER the records that use it (late back-fill)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    _dev_header(b, t0)
    b.define(1, DEVELOPER_DATA_ID, [(1, "byte", 16), (2, "uint16", 1), (3, "uint8", 1)])
    b.data(1, bytes(range(16)), 95, 0)
    b.define(3, RECORD, [(253, "uint32", 1)], dev_fields=[(5, 2, 0)])
    for i in range(3):
        b.data(3, t0 + i, dev_values=[struct.pack("<H", 260 + i)])
    b.define(
        2,
        FIELD_DESCRIPTION,
        [(0, "uint8", 1), (1, "uint8", 1), (2, "uint8", 1), (3, "string", 8), (8, "string", 8)],
    )
    b.data(2, 0, 5, 0x84, "Power", "Watts")
    b.data(3, t0 + 3, dev_values=[struct.pack("<H", 263)])  # resolved in-line
    return b.build()


def dev_index_reused() -> bytes:
    """developer_data_index 0 redefined by a second app mid-file (taxonomy #22c)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    _dev_header(b, t0)
    b.define(1, DEVELOPER_DATA_ID, [(1, "byte", 16), (2, "uint16", 1), (3, "uint8", 1)])
    b.data(1, bytes(range(16)), 95, 0)
    b.define(
        2,
        FIELD_DESCRIPTION,
        [(0, "uint8", 1), (1, "uint8", 1), (2, "uint8", 1), (3, "string", 20), (8, "string", 8)],
    )
    b.data(2, 0, 5, 0x84, "Power", "Watts")
    b.define(3, RECORD, [(253, "uint32", 1)], dev_fields=[(5, 2, 0)])
    b.data(3, t0, dev_values=[struct.pack("<H", 250)])
    b.data(1, bytes(range(16, 32)), 303, 0)  # second app takes index 0 (greenteg)
    b.data(2, 0, 5, 0x84, "Core Temperature", "C")
    b.data(3, t0 + 1, dev_values=[struct.pack("<H", 371)])
    return b.build()


def enhanced_pairs() -> bytes:
    """speed/altitude alongside their enhanced_ twins: agree, disagree, base-absent
    (taxonomy #28)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(
        1,
        RECORD,
        [
            (253, "uint32", 1),
            (6, "uint16", 1),
            (73, "uint32", 1),
            (2, "uint16", 1),
            (78, "uint32", 1),
        ],
    )
    b.data(1, t0, 8333, 8333, (12 + 500) * 5, (12 + 500) * 5)  # agree
    b.data(1, t0 + 1, 60000, 70000, (100 + 500) * 5, (105 + 500) * 5)  # disagree (saturation)
    b.data(1, t0 + 2, None, 71000, None, (106 + 500) * 5)  # base absent
    return b.build()


def _rec_def(b: FitBuilder, local: int = 1) -> None:
    b.define(local, RECORD, [(253, "uint32", 1), (6, "uint16", 1), (3, "uint8", 1)])


def gaps_timers() -> bytes:
    """One file, every gap kind: manual_stop, smart_recording, unknown,
    post_timer — plus a two-interval timer (taxonomy #43/#44/#45/#46)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(4, EVENT, [(253, "uint32", 1), (0, "enum", 1), (1, "enum", 1), (3, "uint32", 1)])
    _rec_def(b)
    b.data(4, t0, 0, 0, 0)  # timer start
    for i in range(60):
        b.data(1, t0 + i, 8333, 140)
    b.data(4, t0 + 60, 0, 1, 0)  # timer stop (manual)
    b.data(4, t0 + 360, 0, 0, 0)  # timer start
    for i in range(360, 420):
        b.data(1, t0 + i, 8333, 141)
    for i in range(445, 455):  # 26s silence: smart_recording
        b.data(1, t0 + i, 8333, 142)
    for i in range(500, 510):  # 46s silence: unknown
        b.data(1, t0 + i, 8333, 143)
    b.data(4, t0 + 510, 0, 4, 0)  # stop_all
    b.data(1, t0 + 520, 0, 90)  # post-timer records (#44)
    b.data(1, t0 + 580, 0, 88)
    return b.build()


def missing_final_stop() -> bytes:
    """Timer started, device died: no stop event at all (taxonomy #45)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(4, EVENT, [(253, "uint32", 1), (0, "enum", 1), (1, "enum", 1), (3, "uint32", 1)])
    b.data(4, t0, 0, 0, 0)
    _rec_def(b)
    for i in range(30):
        b.data(1, t0 + i, 8333, 150)
    return b.build()


def nonmonotonic() -> bytes:
    """GPS resync jumped the clock backwards; plus a duplicate second
    (taxonomy #41/#42)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    _rec_def(b)
    for i in (0, 1, 2, 3, 4, 5):
        b.data(1, t0 + i, 8333, 120 + i)
    b.data(1, t0 + 3, 8333, 200)  # clock jumped back after satellite lock
    b.data(1, t0 + 3, 8333, 201)  # duplicate second
    b.data(1, t0 + 6, 8333, 126)
    b.data(1, t0 + 7, 8333, 127)
    return b.build()


def zwift_local1989() -> bytes:
    """Zwift bug (taxonomy #37/#83): local_timestamp is device-relative junk."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 260, t0)  # manufacturer=zwift
    _rec_def(b)
    for i in range(10):
        b.data(1, t0 + i, 9000, 155)
    b.define(
        6,
        SESSION,
        [
            (253, "uint32", 1),
            (254, "uint16", 1),
            (0, "enum", 1),
            (1, "enum", 1),
            (2, "uint32", 1),
            (5, "enum", 1),
            (6, "enum", 1),
            (7, "uint32", 1),
            (8, "uint32", 1),
            (9, "uint32", 1),
        ],
    )
    b.data(6, t0 + 10, 0, 8, 1, t0, 2, 58, 10000, 10000, 9000)  # virtual_activity
    b.define(
        7,
        ACTIVITY,
        [
            (253, "uint32", 1),
            (0, "uint32", 1),
            (1, "uint16", 1),
            (2, "enum", 1),
            (3, "enum", 1),
            (4, "enum", 1),
            (5, "uint32", 1),
        ],
    )
    b.data(7, t0 + 10, 10000, 1, 0, 26, 1, 7200)  # local_timestamp = 7200 (1989!)
    return b.build()


def old_timestamps() -> bytes:
    """Device never saw GPS time: everything in 2005 (taxonomy #39)."""
    b = FitBuilder()
    t_old = fit_ts(datetime(2005, 6, 1, 9, 0, 0, tzinfo=UTC))
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t_old)
    _rec_def(b)
    for i in range(10):
        b.data(1, t_old + i, 8333, 130)
    return b.build()


def multisport() -> bytes:
    """Triathlon: swim + transition + bike, sessions bounding their own records
    (taxonomy #75)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    _rec_def(b)
    for i in range(0, 100):  # swim: 1.5 m/s
        b.data(1, t0 + i, 1500, 120)
    for i in range(100, 130):  # transition: jog 2 m/s
        b.data(1, t0 + i, 2000, 130)
    for i in range(130, 330):  # bike: 10 m/s
        b.data(1, t0 + i, 10000, 140)
    sess = [
        (253, "uint32", 1),
        (254, "uint16", 1),
        (0, "enum", 1),
        (1, "enum", 1),
        (2, "uint32", 1),
        (5, "enum", 1),
        (6, "enum", 1),
        (7, "uint32", 1),
        (8, "uint32", 1),
        (9, "uint32", 1),
    ]
    b.define(6, SESSION, sess)
    b.data(6, t0 + 100, 0, 8, 1, t0, 5, 18, 99000, 99000, 15000)  # swim, open_water
    b.data(6, t0 + 130, 1, 8, 1, t0 + 100, 3, 0, 29000, 29000, 6000)  # transition
    b.data(6, t0 + 330, 2, 8, 1, t0 + 130, 2, 0, 199000, 199000, 200000)  # bike
    b.define(
        5,
        LAP,
        [
            (253, "uint32", 1),
            (254, "uint16", 1),
            (2, "uint32", 1),
            (7, "uint32", 1),
            (9, "uint32", 1),
        ],
    )
    b.data(5, t0 + 100, 0, t0, 99000, 15000)
    b.data(5, t0 + 330, 1, t0 + 130, 199000, 200000)
    b.define(
        7,
        ACTIVITY,
        [
            (253, "uint32", 1),
            (0, "uint32", 1),
            (1, "uint16", 1),
            (2, "enum", 1),
            (3, "enum", 1),
            (4, "enum", 1),
            (5, "uint32", 1),
        ],
    )
    b.data(7, t0 + 330, 327000, 3, 1, 26, 1, t0 + 330 + 3600)
    return b.build()


def summary_mismatch() -> bytes:
    """Session summary lies: distance, avg power, elapsed all wrong; avg>max too
    (taxonomy #92/#93)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(
        1,
        RECORD,
        [
            (253, "uint32", 1),
            (5, "uint32", 1),
            (6, "uint16", 1),
            (7, "uint16", 1),
            (2, "uint16", 1),
        ],
    )
    dist = 0
    for i in range(120):
        dist += 833
        alt_m = 10 + (i // 10)  # gentle 11 m climb
        b.data(1, t0 + i, dist, 8333, 200, (alt_m + 500) * 5)
    b.define(
        6,
        SESSION,
        [
            (253, "uint32", 1),
            (254, "uint16", 1),
            (0, "enum", 1),
            (1, "enum", 1),
            (2, "uint32", 1),
            (5, "enum", 1),
            (6, "enum", 1),
            (7, "uint32", 1),
            (8, "uint32", 1),
            (9, "uint32", 1),
            (20, "uint16", 1),
            (21, "uint16", 1),
            (22, "uint16", 1),
        ],
    )
    # declares: elapsed 200s (real 119), distance 1500m (real ~991), avg power
    # 250 W (real 200), max power 240 (< avg!), ascent 90 m (real ~9)
    b.data(6, t0 + 120, 0, 8, 1, t0, 2, 0, 200000, 200000, 150000, 250, 240, 90)
    return b.build()


def no_session() -> bytes:
    """Crash before summaries: records + events only (taxonomy #95/#96)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 260, t0)  # zwift crash class
    b.define(12, 12, [(0, "enum", 1), (1, "enum", 1)])  # sport message
    b.data(12, 2, 6)  # cycling / indoor_cycling
    b.define(4, EVENT, [(253, "uint32", 1), (0, "enum", 1), (1, "enum", 1), (3, "uint32", 1)])
    b.data(4, t0, 0, 0, 0)
    _rec_def(b)
    for i in range(90):
        b.data(1, t0 + i, 9000, 145)
    return b.build()


def zero_duration() -> bytes:
    """Session declares zero elapsed while records exist (taxonomy #97)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    _rec_def(b)
    for i in range(20):
        b.data(1, t0 + i, 8333, 140)
    b.define(
        6,
        SESSION,
        [
            (253, "uint32", 1),
            (254, "uint16", 1),
            (0, "enum", 1),
            (1, "enum", 1),
            (2, "uint32", 1),
            (5, "enum", 1),
            (6, "enum", 1),
            (7, "uint32", 1),
            (8, "uint32", 1),
            (9, "uint32", 1),
        ],
    )
    b.data(6, t0 + 20, 0, 8, 1, t0, 2, 0, 0, 0, 16660)
    return b.build()


def gps_spikes() -> bytes:
    """Two bounce spikes (drop) and one sustained tunnel jump (keep) (#53/#54)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(1, RECORD, [(253, "uint32", 1), (0, "sint32", 1), (1, "sint32", 1)])
    lat0, lon0 = 52.37, 4.89
    for i in range(40):
        la, lo = lat0 + i * 1e-5, lon0
        if i in (10, 25):
            la += 0.05  # ~5.5 km teleport for one second — impossible bounce
        if i >= 32:
            lo += 0.005  # tunnel exit: sustained ~350 m jump — legitimate
        b.data(1, t0 + i, semicircles(la), semicircles(lo))
    b.define(
        6,
        SESSION,
        [
            (253, "uint32", 1),
            (254, "uint16", 1),
            (0, "enum", 1),
            (1, "enum", 1),
            (2, "uint32", 1),
            (5, "enum", 1),
            (6, "enum", 1),
            (7, "uint32", 1),
            (8, "uint32", 1),
            (9, "uint32", 1),
        ],
    )
    b.data(6, t0 + 40, 0, 8, 1, t0, 1, 0, 40000, 40000, 12000)  # running
    return b.build()


def null_island() -> bytes:
    """(0,0) fixes and sentinel positions interleaved with valid ones (#51)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(1, RECORD, [(253, "uint32", 1), (0, "sint32", 1), (1, "sint32", 1)])
    for i in range(12):
        if i in (2, 3):
            b.data(1, t0 + i, 0, 0)  # Null Island
        elif i == 5:
            b.data(1, t0 + i, None, None)  # sentinel (decode nulls it)
        else:
            b.data(1, t0 + i, semicircles(52.37 + i * 1e-5), semicircles(4.89))
    return b.build()


def virtual_gps() -> bytes:
    """Watopia coordinates with jumps that would trip the gate — must be exempt
    (taxonomy #57)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 260, t0)  # zwift
    b.define(1, RECORD, [(253, "uint32", 1), (0, "sint32", 1), (1, "sint32", 1)])
    for i in range(10):
        la = -11.64 + (0.1 if i == 5 else 0) + i * 1e-5  # teleport at i=5: kept!
        b.data(1, t0 + i, semicircles(la), semicircles(166.97))
    return b.build()


def treadmill_jump() -> bytes:
    """Treadmill run: accelerometer distance, manual end-of-run correction as a
    final distance jump — legit, must produce no spike complaints (#78)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(1, RECORD, [(253, "uint32", 1), (5, "uint32", 1), (6, "uint16", 1)])
    dist = 0
    for i in range(30):
        dist += 250  # 2.5 m/s accel estimate
        b.data(1, t0 + i, dist, 2500)
    b.data(1, t0 + 30, 120000, 2500)  # user corrected total to 1200 m at the end
    b.define(
        6,
        SESSION,
        [
            (253, "uint32", 1),
            (254, "uint16", 1),
            (0, "enum", 1),
            (1, "enum", 1),
            (2, "uint32", 1),
            (5, "enum", 1),
            (6, "enum", 1),
            (7, "uint32", 1),
            (8, "uint32", 1),
            (9, "uint32", 1),
        ],
    )
    b.data(6, t0 + 31, 0, 8, 1, t0, 1, 1, 31000, 31000, 120000)  # running/treadmill
    return b.build()


def summary_first() -> bytes:
    """Garmin's Dec-2023 'summary first' layout: session/lap/activity BEFORE
    records (taxonomy #50). Broke every order-assuming parser; must not us."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(
        6,
        SESSION,
        [
            (253, "uint32", 1),
            (254, "uint16", 1),
            (0, "enum", 1),
            (1, "enum", 1),
            (2, "uint32", 1),
            (5, "enum", 1),
            (6, "enum", 1),
            (7, "uint32", 1),
            (8, "uint32", 1),
            (9, "uint32", 1),
        ],
    )
    b.data(6, t0 + 40, 0, 8, 1, t0, 2, 0, 40000, 40000, 33320)
    b.define(
        5,
        LAP,
        [
            (253, "uint32", 1),
            (254, "uint16", 1),
            (2, "uint32", 1),
            (7, "uint32", 1),
            (9, "uint32", 1),
        ],
    )
    b.data(5, t0 + 40, 0, t0, 40000, 33320)
    b.define(
        7,
        ACTIVITY,
        [
            (253, "uint32", 1),
            (0, "uint32", 1),
            (1, "uint16", 1),
            (2, "enum", 1),
            (3, "enum", 1),
            (4, "enum", 1),
            (5, "uint32", 1),
        ],
    )
    b.data(7, t0 + 40, 40000, 1, 0, 26, 1, t0 + 40 + 7200)
    b.define(4, EVENT, [(253, "uint32", 1), (0, "enum", 1), (1, "enum", 1), (3, "uint32", 1)])
    b.data(4, t0, 0, 0, 0)
    _rec_def(b)
    dist = 0
    for i in range(40):
        dist += 833
        b.data(1, t0 + i, 8333, 140)
    b.data(4, t0 + 40, 0, 4, 0)
    return b.build()


def csd_legacy() -> bytes:
    """Legacy compressed_speed_distance records incl. a 256 m rollover (#29)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(1, RECORD, [(253, "uint32", 1), (8, "byte", 3)])
    dist_16ths = 4000  # near the 4096 rollover
    for i in range(8):
        speed_raw = 300  # 3.00 m/s
        dist_16ths = (dist_16ths + 48) % 4096  # +3 m per second, wraps mid-run
        b0 = speed_raw & 0xFF
        b1 = ((speed_raw >> 8) & 0x0F) | ((dist_16ths & 0x0F) << 4)
        b2 = (dist_16ths >> 4) & 0xFF
        b.data(1, t0 + i, bytes([b0, b1, b2]))
    return b.build()


def accumulator_wrap() -> bytes:
    """accumulated_power wrapping its uint32 (#30)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(1, RECORD, [(253, "uint32", 1), (29, "uint32", 1)])
    b.data(1, t0, 4294967000)
    b.data(1, t0 + 1, 4294967290)
    b.data(1, t0 + 2, 150)  # wrapped
    b.data(1, t0 + 3, 400)
    return b.build()


def event_subfields() -> bytes:
    """timer events with manual/auto triggers resolved from event.data (#31)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(4, EVENT, [(253, "uint32", 1), (0, "enum", 1), (1, "enum", 1), (3, "uint32", 1)])
    b.data(4, t0, 0, 0, 0)  # manual start
    _rec_def(b)
    for i in range(20):
        b.data(1, t0 + i, 8333, 140)
    b.data(4, t0 + 20, 0, 1, 1)  # AUTO pause
    b.data(4, t0 + 60, 0, 0, 1)
    for i in range(60, 80):
        b.data(1, t0 + i, 8333, 141)
    b.data(4, t0 + 80, 0, 4, 0)
    return b.build()


def sensor_anomalies() -> bytes:
    """HR spikes + flatline, power spike, distance decrease/reset (#59/#62/#63)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(
        1,
        RECORD,
        [(253, "uint32", 1), (3, "uint8", 1), (7, "uint16", 1), (5, "uint32", 1), (6, "uint16", 1)],
    )
    dist = 0
    for i in range(200):
        hr = 250 if i in (5, 6) else 155  # static spikes (#62)
        power = 4000 if i == 10 else 210  # 4 kW spike (#63)
        if i == 150:
            dist = 0  # reset (#59)
        elif i == 100:
            dist -= 500  # decrease (#59)
        else:
            dist += 833
        b.data(1, t0 + i, hr, power, max(dist, 0), 8333)
    for i in range(200, 330):  # flatline 130 s (#62)
        dist += 833
        b.data(1, t0 + i, 166, 210, dist, 8333)
    return b.build()


def pool_swim() -> bytes:
    """Pool swim: lengths, a zero-length artifact, mis-set pool size (#73)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(
        2,
        101,
        [
            (253, "uint32", 1),
            (254, "uint16", 1),
            (0, "enum", 1),
            (1, "enum", 1),
            (2, "uint32", 1),
            (3, "uint32", 1),
            (5, "uint16", 1),
            (7, "enum", 1),
            (12, "enum", 1),
        ],
    )
    t = t0
    for i in range(10):
        b.data(2, t + 30, i, 28, 1, t, 30000, 22, 0, 1)  # active, freestyle, 30s
        t += 30
    b.data(2, t + 1, 10, 28, 1, t, 800, 0, 0, 1)  # 0.8s zero-length artifact
    t += 1
    b.define(
        6,
        SESSION,
        [
            (253, "uint32", 1),
            (254, "uint16", 1),
            (0, "enum", 1),
            (1, "enum", 1),
            (2, "uint32", 1),
            (5, "enum", 1),
            (6, "enum", 1),
            (7, "uint32", 1),
            (8, "uint32", 1),
            (9, "uint32", 1),
            (44, "uint16", 1),
        ],
    )
    # user swam in a 33.3m pool but device is set to 25m: declared distance
    # 11 lengths x 25m = 275m -> implied pool from actives ~25m: make it WRONG:
    # declare 700m over 11 active lengths -> 63.6m implied pool
    b.data(6, t, 0, 8, 1, t0, 5, 17, (t - t0) * 1000, (t - t0) * 1000, 70000, 2500)
    return b.build()


def zero_duration_lap() -> bytes:
    """Double lap-button press: a zero-duration lap among real ones (#94)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    _rec_def(b)
    for i in range(60):
        b.data(1, t0 + i, 8333, 140)
    b.define(
        5,
        LAP,
        [
            (253, "uint32", 1),
            (254, "uint16", 1),
            (2, "uint32", 1),
            (7, "uint32", 1),
            (9, "uint32", 1),
        ],
    )
    b.data(5, t0 + 30, 0, t0, 30000, 25000)
    b.data(5, t0 + 30, 1, t0 + 30, 0, 0)  # the double press
    b.data(5, t0 + 60, 2, t0 + 30, 30000, 25000)
    b.define(
        6,
        SESSION,
        [
            (253, "uint32", 1),
            (254, "uint16", 1),
            (0, "enum", 1),
            (1, "enum", 1),
            (2, "uint32", 1),
            (5, "enum", 1),
            (6, "enum", 1),
            (7, "uint32", 1),
            (8, "uint32", 1),
            (9, "uint32", 1),
        ],
    )
    b.data(6, t0 + 60, 0, 8, 1, t0, 2, 0, 60000, 60000, 50000)
    return b.build()


def empty_shell() -> bytes:
    """Structurally valid, genuinely empty (taxonomy #16, wild 16-byte class)."""
    return FitBuilder().build()


def monitoring_t16() -> bytes:
    """monitoring messages with timestamp_16 crossing a 0x10000 rollover
    (fitdecode#28, fitparse#46)."""
    b = FitBuilder()
    t0 = (fit_ts(T0) & ~0xFFFF) | 0xFFF0  # low 16 bits near rollover
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 15, 1, t0)  # monitoring_a
    b.define(1, 55, [(253, "uint32", 1), (24, "enum", 1)])  # monitoring: ts + activity_type
    b.data(1, t0, 0)
    b.define(2, 55, [(26, "uint16", 1), (3, "uint8", 1)])  # timestamp_16 + heart_rate-ish
    for i in range(1, 6):
        b.data(2, (t0 + i * 8) & 0xFFFF, 60 + i)  # crosses 0xFFFF -> 0x0000
    return b.build()


def hr_plugin() -> bytes:
    """hr messages: full event_timestamp anchor + event_timestamp_12 packed
    deltas incl. a 0xFFF rollover (fitparse#69/#122 class)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    anchor = 0xFFA0  # 1/1024 s units, low 12 bits near rollover
    b.define(1, 132, [(9, "uint32", 1)])  # hr.event_timestamp (scale 1024)
    b.data(1, anchor)
    # eight 12-bit deltas, LSB-first bit stream in 12 bytes:
    deltas = [0xFB0, 0xFC0, 0xFD0, 0x010, 0x020, 0x030, 0x040, 0x050]  # rollover at 0x010
    total = 0
    for i, d in enumerate(deltas):
        total |= d << (12 * i)
    b.define(2, 132, [(10, "byte", 12), (6, "uint8", 8)])  # event_timestamp_12 + filtered_bpm
    b.data(2, total.to_bytes(12, "little"), [120, 121, 122, 123, 124, 125, 126, 127])
    return b.build()


def lr_balance() -> bytes:
    """left_right_balance bit-packed values incl. the exact 0x7F/0x80 cases
    that fooled enum-mappers (fitdecode#38, fit-swift-sdk#13)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(1, RECORD, [(253, "uint32", 1), (7, "uint16", 1), (30, "uint8", 1)])
    b.data(1, t0, 250, 0x80 | 52)  # right flag + 52% right
    b.data(1, t0 + 1, 251, 0x80 | 48)
    b.data(1, t0 + 2, 252, 0x80)  # right flag + 0% (the literal 128 that rendered 'right')
    b.data(1, t0 + 3, 253, None)  # absent
    return b.build()


def multi_string() -> bytes:
    """String array with embedded NULs + junk padding after the final
    terminator (muktihari#623/#436)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 5, 1, t0)  # workout file
    b.define(1, 26, [(8, "string", 16)])  # workout.wkt_name
    b.data(1, b"Open\x00Water\x00\xde\xad\xbe\xef\x00")  # byte-exact 16: strings + junk
    return b.build()


def ts_as_bytes() -> bytes:
    """Field 253 declared as byte[4] (fitdecode#33, Xiaomi->Strava pipeline)."""
    b = FitBuilder()
    t0 = fit_ts(T0)
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(1, RECORD, [(253, "byte", 4), (3, "uint8", 1)])
    for i in range(4):
        b.data(1, (t0 + i).to_bytes(4, "little"), 140 + i)
    return b.build()


def system_time_only() -> bytes:
    """Device never got wall-clock time: all timestamps are seconds since
    power-on (< 0x10000000); relative timeline must survive (fitparse#3/#6)."""
    b = FitBuilder()
    b.define(0, FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, 16444673)  # relative time_created too
    b.define(1, RECORD, [(253, "uint32", 1), (3, "uint8", 1)])
    for i in range(30):
        b.data(1, 16444673 + i, 130 + i % 20)
    return b.build()


def float_sentinel_vs_nan() -> bytes:
    """Exact all-ones float pattern = silent absence; a genuine NaN payload =
    nulled WITH a warning (muktihari#39)."""
    b = FitBuilder()
    b.define(0, FILE_ID, [(0, "enum", 1)])
    b.data(0, 4)
    b.define(1, 4242, [(0, "float32", 1), (1, "float32", 1), (2, "float64", 1)])
    b.data(1, None, float("nan"), 2.5)  # sentinel (silent), NaN (warned), real
    return b.build()


SEEDS: dict[str, object] = {
    "ride_smooth": ride_smooth,
    "run_basic": run_basic,
    "course_file": course_file,
    "workout_file": workout_file,
    "monitoring_file": monitoring_file,
    "summary_only": summary_only,
    "empty_shell": empty_shell,
    "csd_legacy": csd_legacy,
    "accumulator_wrap": accumulator_wrap,
    "event_subfields": event_subfields,
    "sensor_anomalies": sensor_anomalies,
    "pool_swim": pool_swim,
    "zero_duration_lap": zero_duration_lap,
    "monitoring_t16": monitoring_t16,
    "hr_plugin": hr_plugin,
    "lr_balance": lr_balance,
    "multi_string": multi_string,
    "ts_as_bytes": ts_as_bytes,
    "system_time_only": system_time_only,
    "float_sentinel_vs_nan": float_sentinel_vs_nan,
    "summary_first": summary_first,
    "gps_spikes": gps_spikes,
    "null_island": null_island,
    "virtual_gps": virtual_gps,
    "treadmill_jump": treadmill_jump,
    "multisport": multisport,
    "summary_mismatch": summary_mismatch,
    "no_session": no_session,
    "zero_duration": zero_duration,
    "gaps_timers": gaps_timers,
    "missing_final_stop": missing_final_stop,
    "nonmonotonic": nonmonotonic,
    "zwift_local1989": zwift_local1989,
    "old_timestamps": old_timestamps,
    "enhanced_pairs": enhanced_pairs,
    "dev_fields_stryd": dev_fields_stryd,
    "dev_missing_description": dev_missing_description,
    "dev_no_data_id": dev_no_data_id,
    "dev_null_name": dev_null_name,
    "dev_late_description": dev_late_description,
    "dev_index_reused": dev_index_reused,
    "undefined_local": undefined_local,
    "frame_shift": frame_shift,
    "redefinition_stress": redefinition_stress,
    "compressed_ts": compressed_ts,
    "sentinel_soup": sentinel_soup,
    "big_endian_mixed": big_endian_mixed,
    "string_edges": string_edges,
    "hrv_arrays": hrv_arrays,
    "float_fields": float_fields,
    "uint64_fields": uint64_fields,
    "invalid_base_type": invalid_base_type,
}


def build_seed(name: str, **kwargs: object) -> bytes:
    fn = SEEDS[name]
    return fn(**kwargs)  # type: ignore[operator]
