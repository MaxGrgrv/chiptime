"""FIT encoder — canonical wire form (ADR-0006).

Two producers feed `encode_messages`:
- `encodable_from_message`: lossless re-emit of a decoded Message (unknown
  content included; compressed-header timestamps materialized as field 253).
- `encodable_from_profile`: synthesize a message from profile names/values
  (repair's session/activity/events).

This is a programming surface, not a hostile-input surface: bad inputs raise
EncodeError instead of becoming defects.
"""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from chiptime.decode import FIT_EPOCH_UNIX
from chiptime.frames import crc16
from chiptime.message import Message
from chiptime.profile import BASE_TYPES, BASE_TYPES_BY_NAME, ENUMS, MESSAGES

HEADER_SIZE = 14
PROTOCOL_VERSION = 0x20
PROFILE_VERSION = 21141


class EncodeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FieldSpecValue:
    num: int
    base_type: int
    raw: Any  # int | float | bytes | list — wire-ready (sentinel substitution done)
    size: int


@dataclass(frozen=True, slots=True)
class DevSpecValue:
    num: int
    size: int
    dev_index: int
    raw: bytes


@dataclass(frozen=True, slots=True)
class EncodableMessage:
    global_num: int
    specs: tuple[FieldSpecValue, ...]
    dev_specs: tuple[DevSpecValue, ...] = ()

    @property
    def shape(self) -> tuple[Any, ...]:
        return (
            self.global_num,
            tuple((s.num, s.base_type, s.size) for s in self.specs),
            tuple((d.num, d.size, d.dev_index) for d in self.dev_specs),
        )


@dataclass
class _Slots:
    by_shape: dict[tuple[Any, ...], int] = field(default_factory=dict)
    shapes: dict[int, tuple[Any, ...]] = field(default_factory=dict)
    next_slot: int = 0

    def get(self, shape: tuple[Any, ...]) -> tuple[int, bool]:
        """Return (local_id, needs_definition)."""
        if shape in self.by_shape:
            return self.by_shape[shape], False
        local = self.next_slot
        self.next_slot = (self.next_slot + 1) % 16
        old = self.shapes.get(local)
        if old is not None:
            del self.by_shape[old]
        self.by_shape[shape] = local
        self.shapes[local] = shape
        return local, True


def encode_messages(messages: list[EncodableMessage]) -> bytes:
    body = bytearray()
    slots = _Slots()
    for em in messages:
        local, needs_def = slots.get(em.shape)
        if needs_def:
            body += _definition(local, em)
        body += _data(local, em)

    head = bytearray([HEADER_SIZE, PROTOCOL_VERSION])
    head += struct.pack("<H", PROFILE_VERSION)
    head += struct.pack("<I", len(body))
    head += b".FIT"
    head += struct.pack("<H", crc16(bytes(head[:12])))
    out = bytes(head) + bytes(body)
    return out + struct.pack("<H", crc16(out))


def _definition(local: int, em: EncodableMessage) -> bytes:
    if len(em.specs) > 255:
        raise EncodeError(f"message {em.global_num}: too many fields")
    hdr = 0x40 | (0x20 if em.dev_specs else 0x00) | local
    out = bytearray([hdr, 0, 0])  # little-endian always (ADR-0006)
    out += struct.pack("<H", em.global_num)
    out.append(len(em.specs))
    for s in em.specs:
        if not 0 < s.size < 256:
            raise EncodeError(f"field {s.num}: size {s.size} out of range")
        out += bytes([s.num, s.size, s.base_type])
    if em.dev_specs:
        out.append(len(em.dev_specs))
        for d in em.dev_specs:
            out += bytes([d.num, d.size, d.dev_index])
    return bytes(out)


def _data(local: int, em: EncodableMessage) -> bytes:
    out = bytearray([local])
    for s in em.specs:
        bt = BASE_TYPES.get(s.base_type)
        if bt is None or bt.struct_code is None:  # string/byte/unknown → raw bytes
            raw = s.raw if isinstance(s.raw, bytes) else bytes(s.raw)
            if len(raw) > s.size:
                raise EncodeError(f"field {s.num}: {len(raw)} bytes exceeds size {s.size}")
            out += (
                raw + b"\xff" * (s.size - len(raw))
                if bt is None
                else (raw + b"\x00" * (s.size - len(raw)))
            )
            continue
        count = s.size // bt.size
        vals = s.raw if isinstance(s.raw, (list, tuple)) else [s.raw]
        if len(vals) > count:
            raise EncodeError(f"field {s.num}: {len(vals)} values exceed count {count}")
        vals = list(vals) + [None] * (count - len(vals))
        for v in vals:
            if v is None:
                if bt.name in ("float32", "float64"):
                    # the exact invalid pattern, not an arbitrary NaN (muktihari#39)
                    out += b"\xff" * bt.size
                    continue
                v = _invalid_raw(bt.name)
            try:
                out += struct.pack("<" + bt.struct_code, v)
            except struct.error as exc:
                raise EncodeError(f"field {s.num}: {v!r} does not fit {bt.name}") from exc
    for d in em.dev_specs:
        if len(d.raw) != d.size:
            raise EncodeError(f"dev field {d.num}: {len(d.raw)} bytes != size {d.size}")
        out += d.raw
    return bytes(out)


def _invalid_raw(bt_name: str) -> int | float:
    from chiptime.profile.base_types import _SIGNED_INVALID
    from chiptime.profile.base_types import BASE_TYPES_BY_NAME as _BT

    if bt_name in ("float32", "float64"):
        return float("nan")  # canonical invalid pattern via NaN packing
    if bt_name in _SIGNED_INVALID:
        return _SIGNED_INVALID[bt_name]
    inv = _BT[bt_name].invalid
    assert inv is not None
    return inv


# ── producers ───────────────────────────────────────────────────────────────


def encodable_from_message(msg: Message) -> EncodableMessage:
    """Lossless re-emit from a decoded message's wire definition + raw values."""
    if msg.wire is None:
        raise EncodeError(f"message {msg.name} has no wire definition; use encodable_from_profile")
    by_num: dict[int, Any] = {}
    dev_by_key: dict[tuple[int, int], Any] = {}
    mdef = MESSAGES.get(msg.global_num)
    name_to_num = {f.name: n for n, f in mdef.fields.items()} if mdef else {}
    for fname, fv in msg.fields.items():
        if fv.developer is not None:
            key = (fv.developer.developer_data_index, fv.developer.field_definition_number)
            dev_by_key[key] = fv.raw
            continue
        if fname == "timestamp":
            by_num[253] = fv.raw
        elif fname in name_to_num:  # profile name wins (field_description has
            by_num[name_to_num[fname]] = fv.raw  # a real field NAMED field_definition_number)
        elif (m := re.fullmatch(r"field_(\d+)", fname)) is not None:
            by_num[int(m.group(1))] = fv.raw
    specs: list[FieldSpecValue] = []
    seen_253 = False
    for ws in msg.wire.fields:
        seen_253 = seen_253 or ws.num == 253
        specs.append(FieldSpecValue(ws.num, ws.base_type, by_num.get(ws.num), ws.size))
    if not seen_253 and "timestamp" in msg.fields:
        # compressed-header timestamp materialized (ADR-0006 §2)
        ts_raw = msg.fields["timestamp"].raw
        specs.append(FieldSpecValue(253, 0x86, ts_raw, 4))
    dev_specs = tuple(
        DevSpecValue(
            ds.num,
            ds.size,
            ds.dev_data_index,
            _dev_bytes(dev_by_key.get((ds.dev_data_index, ds.num)), ds.size),
        )
        for ds in msg.wire.dev_fields
    )
    return EncodableMessage(msg.global_num, tuple(specs), dev_specs)


def _dev_bytes(raw: Any, size: int) -> bytes:
    """Re-pack a decoded dev-field raw value into its wire bytes."""
    if raw is None:
        return b"\xff" * size
    if isinstance(raw, bytes):
        if len(raw) != size:
            raise EncodeError(f"dev field bytes {len(raw)} != size {size}")
        return raw
    if isinstance(raw, int):
        return raw.to_bytes(size, "little", signed=raw < 0)
    if isinstance(raw, float):
        code = {4: "<f", 8: "<d"}.get(size)
        if code is None:
            raise EncodeError(f"float dev field with size {size}")
        return struct.pack(code, raw)
    if isinstance(raw, (list, tuple)):
        if not raw:
            return b"\xff" * size
        per = size // len(raw)
        return b"".join(_dev_bytes(v, per) for v in raw)
    raise EncodeError(f"cannot re-pack dev value {raw!r}")


def encodable_from_profile(global_num: int, values: dict[str, Any]) -> EncodableMessage:
    """Synthesize a message from profile field names + semantic values."""
    mdef = MESSAGES.get(global_num)
    if mdef is None:
        raise EncodeError(
            f"unknown global message {global_num}; profile synthesis needs a known message"
        )
    by_name = {f.name: f for f in mdef.fields.values()}
    specs: list[FieldSpecValue] = []
    for fname, value in values.items():
        fdef = by_name.get(fname)
        if fdef is None:
            raise EncodeError(f"{mdef.name} has no field {fname!r}")
        bt_name, raw, size = _reverse(fdef, value)
        specs.append(FieldSpecValue(fdef.num, BASE_TYPES_BY_NAME[bt_name].byte, raw, size))
    return EncodableMessage(global_num, tuple(specs))


# Wire types for profile-synthesized fields (canonical choices).
_SYNTH_TYPES: dict[str, str] = {
    "timestamp": "uint32",
    "start_time": "uint32",
    "local_timestamp": "uint32",
    "time_created": "uint32",
}


def _reverse(fdef: Any, value: Any) -> tuple[str, Any, int]:
    kind = fdef.kind
    if kind in ("date_time", "local_date_time"):
        if isinstance(value, datetime):
            raw = int(value.timestamp()) - FIT_EPOCH_UNIX
        elif isinstance(value, int):
            raw = value
        else:
            raise EncodeError(f"{fdef.name}: expected datetime or FIT seconds")
        return "uint32", raw, 4
    if kind.startswith("enum:"):
        mapping = ENUMS.get(kind.removeprefix("enum:"), {})
        if isinstance(value, str):
            rev = {v: k for k, v in mapping.items()}
            if value not in rev:
                raise EncodeError(f"{fdef.name}: unknown enum name {value!r}")
            raw = rev[value]
        else:
            raw = int(value)
        ebt = "uint16" if fdef.name in ("manufacturer", "manufacturer_id") else "enum"
        return ebt, raw, BASE_TYPES_BY_NAME[ebt].size
    if kind == "string":
        sraw = str(value).encode("utf-8") + b"\x00"
        return "string", sraw, len(sraw)
    if kind == "bytes":
        braw = bytes(value)
        return "byte", braw, len(braw)
    # numbers: reverse scale/offset; choose a wide-enough canonical type
    raw_num = round((float(value) + fdef.offset) * fdef.scale)
    bt = _SYNTH_TYPES.get(fdef.name)
    if bt is None:
        if fdef.name in ("message_index", "num_laps", "first_lap_index"):
            bt = "uint16"
        elif raw_num < 0:
            bt = "sint32"
        elif raw_num <= 0xFE:
            bt = "uint8"
        elif raw_num <= 0xFFFE:
            bt = "uint16"
        else:
            bt = "uint32"
    return bt, raw_num, BASE_TYPES_BY_NAME[bt].size
