"""FIT profile: base types, generated breadth + hand-authored verified core.

Merge policy (F18): generated tables (full SDK breadth, ADR-0004) form the
base; the hand-authored, fitdecode-verified core overrides per-field and
per-enum-value where both exist. Unknown-tolerance is unchanged — anything
absent still decodes as unknown_* (contract #6).
"""

from chiptime.profile.base_types import BASE_TYPES, BASE_TYPES_BY_NAME, BaseType, is_invalid
from chiptime.profile.core import ENUMS as _CORE_ENUMS
from chiptime.profile.core import MESSAGES as _CORE_MESSAGES
from chiptime.profile.core import SEMICIRCLE_SCALE, FieldDef, MessageDef
from chiptime.profile.generated import (
    GENERATED_ENUMS,
    GENERATED_MESSAGES,
    GENERATED_SDK_VERSION,
)


def _merge_messages() -> dict[int, MessageDef]:
    out: dict[int, MessageDef] = {}
    for num in sorted(set(GENERATED_MESSAGES) | set(_CORE_MESSAGES)):
        gen = GENERATED_MESSAGES.get(num)
        core = _CORE_MESSAGES.get(num)
        if gen is None:
            assert core is not None
            out[num] = core
            continue
        if core is None:
            out[num] = gen
            continue
        fields = dict(gen.fields)
        fields.update(core.fields)  # verified core wins per-field
        out[num] = MessageDef(num, core.name, fields)
    return out


def _merge_enums() -> dict[str, dict[int, str]]:
    out: dict[str, dict[int, str]] = {}
    for name in sorted(set(GENERATED_ENUMS) | set(_CORE_ENUMS)):
        merged = dict(GENERATED_ENUMS.get(name, {}))
        merged.update(_CORE_ENUMS.get(name, {}))
        out[name] = merged
    return out


MESSAGES: dict[int, MessageDef] = _merge_messages()
ENUMS: dict[str, dict[int, str]] = _merge_enums()

__all__ = [
    "BASE_TYPES",
    "BASE_TYPES_BY_NAME",
    "ENUMS",
    "GENERATED_SDK_VERSION",
    "MESSAGES",
    "SEMICIRCLE_SCALE",
    "BaseType",
    "FieldDef",
    "MessageDef",
    "is_invalid",
]
