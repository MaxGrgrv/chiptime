"""Wire-level frame reader. Never raises on content (ADR-0003).

Reads ONE FIT stream (header + body + CRC trailer) from `data` starting at
`offset`; chained files are handled by the caller reading again from
EndOfStream.consumed. Structural defects currently stop the stream (prefix
salvage); F5 replaces the stop with resynchronization.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass

from chiptime.errors import Defect
from chiptime.profile.base_types import BASE_TYPES

MAGIC = b".FIT"

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


def _nibble_step(crc: int, byte: int) -> int:
    tmp = CRC_TABLE[crc & 0xF]
    crc = (crc >> 4) & 0x0FFF
    crc = crc ^ tmp ^ CRC_TABLE[byte & 0xF]
    tmp = CRC_TABLE[crc & 0xF]
    crc = (crc >> 4) & 0x0FFF
    return crc ^ tmp ^ CRC_TABLE[(byte >> 4) & 0xF]


# F20: byte-wise table composed from the FIT nibble algorithm. The identity
# step(crc, b) == (crc >> 8) ^ T[(crc ^ b) & 0xFF] is property-verified in
# tests; ~2x on megabyte bodies with bit-identical results.
_CRC256 = [_nibble_step(0, b) for b in range(256)]


def crc16(data: bytes, crc: int = 0) -> int:
    table = _CRC256
    for byte in data:
        crc = (crc >> 8) ^ table[(crc ^ byte) & 0xFF]
    return crc


@dataclass(frozen=True, slots=True)
class FileHeader:
    offset: int
    size: int
    protocol_version: int
    profile_version: int
    data_size: int
    magic_ok: bool
    crc_declared: int | None  # None: 12-byte header has no CRC
    crc_ok: bool | None  # None: absent or zero (legal skip, taxonomy #5)


@dataclass(frozen=True, slots=True)
class FieldSpec:
    num: int
    size: int
    base_type: int


@dataclass(frozen=True, slots=True)
class DevFieldSpec:
    num: int
    size: int
    dev_data_index: int


@dataclass(frozen=True, slots=True)
class DefinitionFrame:
    offset: int
    local_id: int
    global_num: int
    big_endian: bool
    fields: tuple[FieldSpec, ...]
    dev_fields: tuple[DevFieldSpec, ...]

    @property
    def payload_size(self) -> int:
        return sum(f.size for f in self.fields) + sum(f.size for f in self.dev_fields)


@dataclass(frozen=True, slots=True)
class DataFrame:
    offset: int
    local_id: int
    definition: DefinitionFrame
    payload: bytes
    time_offset: int | None  # set for compressed-timestamp headers (taxonomy #21)


@dataclass(frozen=True, slots=True)
class CrcFrame:
    offset: int
    declared: int
    computed: int
    ok: bool


@dataclass(frozen=True, slots=True)
class SkippedBytes:
    offset: int
    length: int
    reason: str


@dataclass(frozen=True, slots=True)
class EndOfStream:
    consumed: int  # absolute offset just past this FIT stream


FrameEvent = (
    FileHeader | DefinitionFrame | DataFrame | CrcFrame | SkippedBytes | Defect | EndOfStream
)

MAX_RESYNCS = 64  # pathological files degrade to prefix salvage, never hang
PREAMBLE_SCAN_LIMIT = 4096
_MAX_DEF_PAYLOAD = 2048  # implausibly large record payloads reject a resync candidate


def _plausible_definition(data: bytes, p: int, end: int) -> tuple[int, int, int] | None:
    """If a plausible definition frame starts at p, return (end_offset, local_id,
    payload_size); else None. Stricter than the main reader: reserved bit 4 must
    be clear, every base type known, sizes positive multiples."""
    hdr = data[p]
    if hdr & 0x80 or not hdr & 0x40 or hdr & 0x10:
        return None
    has_dev = bool(hdr & 0x20)
    q = p + 1
    if q + 5 > end:
        return None
    if data[q + 1] not in (0, 1):
        return None
    nf = data[q + 4]
    if nf < 1:  # modern Garmin definitions exceed 100 fields (tormoder#43 class)
        return None
    q += 5
    if q + nf * 3 > end:
        return None
    total = 0
    for _ in range(nf):
        size, btb = data[q + 1], data[q + 2]
        bt = BASE_TYPES.get(btb)
        if bt is None or size == 0 or (bt.struct_code is not None and size % bt.size):
            return None
        total += size
        q += 3
    if has_dev:
        if q + 1 > end:
            return None
        nd = data[q]
        if nd > 32:
            return None
        q += 1
        if q + nd * 3 > end:
            return None
        for _ in range(nd):
            total += data[q + 1]
            q += 3
    if total > _MAX_DEF_PAYLOAD:
        return None
    return q, hdr & 0x0F, total


def _lookahead_ok(
    data: bytes,
    q: int,
    end: int,
    local_defs: dict[int, DefinitionFrame],
    cand_local: int,
    cand_size: int,
) -> bool:
    """One-frame lookahead: the bytes after a candidate definition must
    themselves start a plausible frame."""
    if q >= end:
        return True
    b = data[q]
    if b & 0x80:  # compressed data
        local = (b >> 5) & 0x03
    elif b & 0x40:  # another definition header (shallow check)
        return not b & 0x10
    else:
        local = b & 0x0F
    if local == cand_local:
        size = cand_size
    elif local in local_defs:
        size = local_defs[local].payload_size
    else:
        return False
    return q + 1 + size <= end


def _find_next_definition(
    data: bytes, from_pos: int, end: int, local_defs: dict[int, DefinitionFrame]
) -> int | None:
    for p in range(from_pos, end):
        cand = _plausible_definition(data, p, end)
        if cand is None:
            continue
        q, local, size = cand
        if _lookahead_ok(data, q, end, local_defs, local, size):
            return p
    return None


def read_stream(data: bytes, *, offset: int = 0) -> Iterator[FrameEvent]:
    n = len(data)
    start = offset
    avail = n - start

    if avail == 0:
        yield Defect("FIT_EMPTY", "file contains no bytes", start, "fatal")
        yield EndOfStream(n)
        return
    if avail < 12:
        yield Defect(
            "FIT_TOO_SMALL", f"only {avail} bytes; smallest valid FIT header is 12", start, "fatal"
        )
        yield EndOfStream(n)
        return

    hsize = data[start]
    magic_ok = data[start + 8 : start + 12] == MAGIC
    if hsize not in (12, 14) and not magic_ok:
        # Preamble garbage before the real header (taxonomy #9, Edge 1050 class):
        # scan ahead for the magic and re-anchor.
        m = data.find(MAGIC, start, start + PREAMBLE_SCAN_LIMIT)
        if m - 8 > start and 12 <= data[m - 8] <= 64:
            skipped = m - 8 - start
            yield Defect(
                "FIT_HEADER_INVALID",
                f"{skipped} garbage byte(s) before the FIT header",
                start,
                "structural",
            )
            yield SkippedBytes(start, skipped, "preamble-garbage")
            start = m - 8
            avail = n - start
            hsize = data[start]
            magic_ok = True
    if hsize not in (12, 14):
        if magic_ok and 12 <= hsize <= 64 and start + hsize <= n:
            yield Defect(
                "FIT_HEADER_INVALID",
                f"nonstandard header size {hsize}; '.FIT' magic present, proceeding",
                start,
                "structural",
            )
        elif magic_ok:
            yield Defect(
                "FIT_HEADER_INVALID",
                f"invalid header size {hsize}; '.FIT' magic present, assuming 14",
                start,
                "structural",
            )
            hsize = 14 if avail >= 14 else 12
        else:
            yield Defect(
                "NOT_FIT_FORMAT",
                f"no '.FIT' magic and invalid header size {hsize}",
                start,
                "fatal",
            )
            yield EndOfStream(n)
            return
    elif not magic_ok:
        yield Defect(
            "FIT_HEADER_INVALID",
            "'.FIT' magic missing from header; proceeding",
            start,
            "structural",
        )

    protocol = data[start + 1]
    profile_ver = struct.unpack_from("<H", data, start + 2)[0]
    data_size = struct.unpack_from("<I", data, start + 4)[0]

    crc_declared: int | None = None
    crc_ok: bool | None = None
    if hsize >= 14 and start + 14 <= n:
        crc_declared = struct.unpack_from("<H", data, start + 12)[0]
        if crc_declared != 0:  # 0x0000 = legal "no check" (taxonomy #5)
            computed_hdr = crc16(data[start : start + 12])
            crc_ok = computed_hdr == crc_declared
            if not crc_ok:
                yield Defect(
                    "FIT_HEADER_CRC_MISMATCH",
                    f"header CRC 0x{crc_declared:04X} != computed 0x{computed_hdr:04X}",
                    start + 12,
                    "structural",
                )

    yield FileHeader(start, hsize, protocol, profile_ver, data_size, magic_ok, crc_declared, crc_ok)

    body_start = start + hsize
    declared_end = body_start + data_size
    truncated_declared = declared_end > n
    end = n if truncated_declared else declared_end
    if not truncated_declared and data_size == 0 and n - body_start > 2:
        yield Defect(
            "FIT_DATA_SIZE_MISMATCH",
            f"header declares 0 data bytes but {n - body_start} are present; trusting content",
            start + 4,
            "structural",
        )
        end = n - 2

    local_defs: dict[int, DefinitionFrame] = {}
    local_sizes: dict[int, int] = {}  # F20: avoid per-frame payload_size sums
    pos = body_start
    stopped = False
    resyncs = 0

    def _resync(bad_pos: int, code: str) -> tuple[SkippedBytes, int]:
        nxt = None
        if resyncs < MAX_RESYNCS:
            nxt = _find_next_definition(data, bad_pos + 1, end, local_defs)
        if nxt is None:
            return SkippedBytes(bad_pos, end - bad_pos, code), end
        return SkippedBytes(bad_pos, nxt - bad_pos, code), nxt

    while pos < end:
        hdr = data[pos]
        if hdr & 0x80:  # compressed-timestamp data message
            local = (hdr >> 5) & 0x03
            toff = hdr & 0x1F
            df = local_defs.get(local)
            if df is None:
                yield Defect(
                    "FIT_UNDEFINED_LOCAL_TYPE",
                    f"compressed data message references undefined local type {local}",
                    pos,
                    "structural",
                )
                skip, pos = _resync(pos, "FIT_UNDEFINED_LOCAL_TYPE")
                resyncs += 1
                yield skip
                continue
            size = local_sizes[local]
            if pos + 1 + size > end:
                yield Defect(
                    "FIT_TRUNCATED",
                    f"record at byte {pos} needs {size} payload bytes; only {end - pos - 1} remain",
                    pos,
                    "structural",
                )
                stopped = True
                break
            yield DataFrame(pos, local, df, data[pos + 1 : pos + 1 + size], toff)
            pos += 1 + size
        elif hdr & 0x40:  # definition message
            local = hdr & 0x0F
            has_dev = bool(hdr & 0x20)
            p = pos + 1
            if p + 5 > end:
                yield Defect(
                    "FIT_TRUNCATED", "file ends inside a definition message", pos, "structural"
                )
                stopped = True
                break
            arch = data[p + 1]
            if arch not in (0, 1):
                yield Defect(
                    "FIT_DEFINITION_INVALID",
                    f"architecture byte 0x{arch:02X} is neither little- nor big-endian",
                    p + 1,
                    "structural",
                )
                skip, pos = _resync(pos, "FIT_DEFINITION_INVALID")
                resyncs += 1
                yield skip
                continue
            big = arch == 1
            global_num = struct.unpack_from(">H" if big else "<H", data, p + 2)[0]
            nf = data[p + 4]
            p += 5
            if p + nf * 3 > end:
                yield Defect(
                    "FIT_TRUNCATED", "file ends inside a definition's field list", pos, "structural"
                )
                stopped = True
                break
            fields = tuple(
                FieldSpec(data[p + i * 3], data[p + i * 3 + 1], data[p + i * 3 + 2])
                for i in range(nf)
            )
            p += nf * 3
            dev_fields: tuple[DevFieldSpec, ...] = ()
            if has_dev:
                if p + 1 > end:
                    yield Defect(
                        "FIT_TRUNCATED",
                        "file ends before the developer-field count byte",
                        pos,
                        "structural",
                    )
                    stopped = True
                    break
                nd = data[p]
                p += 1
                if p + nd * 3 > end:
                    yield Defect(
                        "FIT_TRUNCATED",
                        "file ends inside a definition's developer-field list",
                        pos,
                        "structural",
                    )
                    stopped = True
                    break
                dev_fields = tuple(
                    DevFieldSpec(data[p + i * 3], data[p + i * 3 + 1], data[p + i * 3 + 2])
                    for i in range(nd)
                )
                p += nd * 3
            frame = DefinitionFrame(pos, local, global_num, big, fields, dev_fields)
            local_defs[local] = frame  # redefinition is legal and common (taxonomy #20)
            local_sizes[local] = frame.payload_size
            yield frame
            pos = p
        else:  # normal data message
            local = hdr & 0x0F
            df = local_defs.get(local)
            if df is None:
                yield Defect(
                    "FIT_UNDEFINED_LOCAL_TYPE",
                    f"data message references undefined local type {local}",
                    pos,
                    "structural",
                )
                skip, pos = _resync(pos, "FIT_UNDEFINED_LOCAL_TYPE")
                resyncs += 1
                yield skip
                continue
            size = local_sizes[local]
            if pos + 1 + size > end:
                yield Defect(
                    "FIT_TRUNCATED",
                    f"record at byte {pos} needs {size} payload bytes; only {end - pos - 1} remain",
                    pos,
                    "structural",
                )
                stopped = True
                break
            yield DataFrame(pos, local, df, data[pos + 1 : pos + 1 + size], None)
            pos += 1 + size

    if stopped:
        # Truncation only: the bytes simply end; nothing to resynchronize into.
        yield EndOfStream(n)
        return

    if truncated_declared:
        yield Defect(
            "FIT_TRUNCATED",
            f"header declares {data_size} data bytes; only {n - body_start} are present",
            n,
            "structural",
        )
        yield EndOfStream(n)
        return

    if end + 2 <= n:
        declared_crc = struct.unpack_from("<H", data, end)[0]
        computed = crc16(data[start:end])
        ok = declared_crc == computed
        if not ok:
            if declared_crc == 0:  # triage (#4 depth): never-finalized write
                why = "trailer is 0x0000: unterminated-write class"
            elif resyncs or stopped:
                why = "stream also had structural damage: storage corruption class"
            else:
                why = (
                    "content decodes cleanly: in-place corruption or"
                    " encoder CRC laziness (fitparse #9 class)"
                )
            yield Defect(
                "FIT_CRC_MISMATCH",
                f"file CRC 0x{declared_crc:04X} != computed 0x{computed:04X} ({why})",
                end,
                "structural",
            )
        yield CrcFrame(end, declared_crc, computed, ok)
        yield EndOfStream(end + 2)
    else:
        yield Defect(
            "FIT_CRC_MISSING", "no room for the 2-byte file CRC after the data", end, "structural"
        )
        yield EndOfStream(n)


# Re-export for decode.py's per-field bounds logic.
__all__ = [
    "BASE_TYPES",
    "CrcFrame",
    "DataFrame",
    "DefinitionFrame",
    "DevFieldSpec",
    "EndOfStream",
    "FieldSpec",
    "FileHeader",
    "FrameEvent",
    "SkippedBytes",
    "crc16",
    "read_stream",
]
