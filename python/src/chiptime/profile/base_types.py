"""FIT base types: wire sizes, struct codes, and per-type invalid sentinels.

The definition frame's base-type byte is authoritative for decoding width;
bit 7 marks multi-byte (endian-sensitive) types, bits 0-4 the type number.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BaseType:
    byte: int
    name: str
    size: int
    struct_code: str | None  # None for string/byte (handled specially)
    invalid: int | None  # sentinel meaning "absent" (taxonomy #26); None → n/a


_TYPES = [
    BaseType(0x00, "enum", 1, "B", 0xFF),
    BaseType(0x01, "sint8", 1, "b", 0x7F),
    BaseType(0x02, "uint8", 1, "B", 0xFF),
    BaseType(0x83, "sint16", 2, "h", 0x7FFF),
    BaseType(0x84, "uint16", 2, "H", 0xFFFF),
    BaseType(0x85, "sint32", 4, "i", 0x7FFFFFFF),
    BaseType(0x86, "uint32", 4, "I", 0xFFFFFFFF),
    BaseType(0x07, "string", 1, None, None),
    BaseType(0x88, "float32", 4, "f", 0xFFFFFFFF),
    BaseType(0x89, "float64", 8, "d", 0xFFFFFFFFFFFFFFFF),
    BaseType(0x0A, "uint8z", 1, "B", 0x00),
    BaseType(0x8B, "uint16z", 2, "H", 0x0000),
    BaseType(0x8C, "uint32z", 4, "I", 0x00000000),
    BaseType(0x0D, "byte", 1, None, None),
    BaseType(0x8E, "sint64", 8, "q", 0x7FFFFFFFFFFFFFFF),
    BaseType(0x8F, "uint64", 8, "Q", 0xFFFFFFFFFFFFFFFF),
    BaseType(0x90, "uint64z", 8, "Q", 0x0000000000000000),
]

BASE_TYPES: dict[int, BaseType] = {t.byte: t for t in _TYPES}
BASE_TYPES_BY_NAME: dict[str, BaseType] = {t.name: t for t in _TYPES}

# Signed sentinels arrive as negative values after struct unpack; precompute.
_SIGNED_INVALID = {
    "sint8": 0x7F,
    "sint16": 0x7FFF,
    "sint32": 0x7FFFFFFF,
    "sint64": 0x7FFFFFFFFFFFFFFF,
}


def is_invalid(bt: BaseType, value: int | float) -> bool:
    """True when the wire value is the base type's 'invalid' sentinel."""
    if bt.invalid is None:
        return False
    if bt.name in ("float32", "float64"):
        # Sentinel is the all-ones bit pattern; it unpacks as NaN. Any NaN
        # is unusable anyway; the caller distinguishes NaN-vs-sentinel for
        # diagnostics via bit inspection if needed.
        return value != value
    return value == _SIGNED_INVALID.get(bt.name, bt.invalid)
