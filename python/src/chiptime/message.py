"""Decoded message types — the lossless middle layer between wire and semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from chiptime.frames import DefinitionFrame


@dataclass(frozen=True, slots=True)
class DevFieldOrigin:
    """Where a developer field came from (resolved in F6)."""

    developer_data_index: int
    field_definition_number: int
    application_id: str | None = None  # hex, from developer_data_id
    vendor: str | None = None  # manufacturer name, e.g. "stryd"
    canonical_name: str | None = None  # registry promotion for stream naming


@dataclass(frozen=True, slots=True)
class FieldValue:
    """One decoded field. `value` is scaled/normalized with sentinels → None;
    `raw` is the wire value (kept for round-trips and include_raw output)."""

    value: Any | None
    raw: Any | None = None
    units: str | None = None
    developer: DevFieldOrigin | None = None


@dataclass(frozen=True, slots=True)
class Message:
    """A decoded FIT data message, unknown-tolerant (contract #6)."""

    global_num: int
    name: str
    local_id: int
    byte_offset: int
    fields: dict[str, FieldValue] = field(default_factory=dict)
    wire: DefinitionFrame | None = None  # retained for lossless re-encoding (ADR-0006)

    def get(self, name: str) -> Any | None:
        fv = self.fields.get(name)
        return fv.value if fv is not None else None

    def get_raw(self, name: str) -> Any | None:
        fv = self.fields.get(name)
        return fv.raw if fv is not None else None
