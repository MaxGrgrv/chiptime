"""User-directed metadata edits with a validated round-trip (F26).

The distinction that governs this module (PRD §5): chiptime never *infers*
intent and never mutates a file on its own — but when the user names an
edit explicitly, it is performed, recorded in `provenance[]`, and the
result is re-parsed in strict mode to prove the file is still sound.

Metadata only: this module never touches a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import chiptime
from chiptime.decode import fit_ts_to_iso, fit_ts_to_iso_local
from chiptime.encode import encodable_from_message, encode_messages
from chiptime.errors import Diagnostic, FitError, ProvenanceEntry
from chiptime.message import FieldValue, Message
from chiptime.profile import BASE_TYPES, ENUMS, MESSAGES
from chiptime.result import Mode, ParseResult

Source = Any

# uint32 range; 0xFFFFFFFF is the invalid sentinel and must never be written
# as a real value (contract #4), so the usable ceiling is one below it.
TS_MIN = 0
TS_MAX = 0xFFFFFFFE

# The recording device is device_index 0 by convention; other entries are
# sensors (a heart-rate strap did not create the file).
CREATOR_DEVICE_INDEX = 0


class EditError(FitError):
    """A requested edit cannot be performed; no bytes are written."""


@dataclass(slots=True)
class EditResult:
    """The edited file plus proof of what changed.

    Attributes:
        data: The edited ``.fit`` bytes — write them to disk as-is.
        provenance: One entry per edit performed, with before/after values.
        warnings: Non-fatal observations (e.g. a sport/sub-sport pair worth
            a second look). chiptime flags; it does not silently fix.
        output_strict_ok: Self-check — the output re-parsed in strict mode.
        parse_result: The parse of the *input*, for inspection.
    """

    data: bytes
    provenance: list[ProvenanceEntry] = field(default_factory=list)
    warnings: list[Diagnostic] = field(default_factory=list)
    output_strict_ok: bool = False
    parse_result: ParseResult | None = None


def _reverse_enum(enum_name: str) -> dict[str, int]:
    """name → value, lowest value wins on aliases (deterministic)."""
    out: dict[str, int] = {}
    for num, name in sorted(ENUMS.get(enum_name, {}).items()):
        out.setdefault(name, num)
    return out


def _enum_raw(enum_name: str, value: str | int) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value  # raw numbers pass through: the ecosystem trades in them
    raw = _reverse_enum(enum_name).get(str(value))
    if raw is None:
        raise EditError(
            "UNKNOWN_ENUM_NAME",
            f"{value!r} is not a known {enum_name} value",
            suggestion=f"pass a raw number instead, or see `chiptime codes` for {enum_name}",
        )
    return raw


def _field_kinds(global_num: int) -> dict[str, str]:
    mdef = MESSAGES.get(global_num)
    return {f.name: f.kind for f in mdef.fields.values()} if mdef else {}


def _set(msg: Message, name: str, raw: Any, value: Any) -> Message:
    """Return a copy of `msg` with one field replaced (never mutates input)."""
    old = msg.fields.get(name)
    fields = dict(msg.fields)
    fields[name] = FieldValue(value=value, raw=raw, units=old.units if old else None)
    return replace(msg, fields=fields)


def _prov(code: str, scope: str, detail: str, data: dict[str, Any]) -> ProvenanceEntry:
    return ProvenanceEntry(code=code, action="reinterpreted", scope=scope, detail=detail, data=data)


def _edit_sport(
    messages: list[Message], sport: str | int | None, sub_sport: str | int | None
) -> tuple[list[Message], list[ProvenanceEntry], list[Diagnostic]]:
    """Apply sport/sub_sport everywhere the profile declares them, so the
    file cannot end up internally contradictory."""
    prov: list[ProvenanceEntry] = []
    warns: list[Diagnostic] = []
    sport_raw = _enum_raw("sport", sport) if sport is not None else None
    sport_name = ENUMS.get("sport", {}).get(sport_raw, sport_raw) if sport_raw is not None else None
    sub_raw = _enum_raw("sub_sport", sub_sport) if sub_sport is not None else None
    sub_name = ENUMS.get("sub_sport", {}).get(sub_raw, sub_raw) if sub_raw is not None else None

    out: list[Message] = []
    for i, m in enumerate(messages):
        kinds = _field_kinds(m.global_num)
        new = m
        if sport_raw is not None and "sport" in kinds and "sport" in m.fields:
            before = m.fields["sport"].value
            new = _set(new, "sport", sport_raw, sport_name)
            prov.append(
                _prov(
                    "SPORT_EDITED",
                    f"message[{i}].{m.name}.sport",
                    f"sport {before!r} → {sport_name!r} (explicit user edit)",
                    {"before": before, "after": sport_name},
                )
            )
            existing_sub = m.fields.get("sub_sport")
            if (
                sub_raw is None
                and existing_sub is not None
                and existing_sub.value not in (None, "generic")
            ):
                warns.append(
                    Diagnostic(
                        code="SPORT_PAIR_IMPLAUSIBLE",
                        detail=(
                            f"sport changed to {sport_name!r} while sub_sport stays "
                            f"{existing_sub.value!r}; pass sub_sport to change it"
                        ),
                        scope=f"message[{i}].{m.name}",
                    )
                )
        if sub_raw is not None and "sub_sport" in kinds and "sub_sport" in m.fields:
            before = m.fields["sub_sport"].value
            new = _set(new, "sub_sport", sub_raw, sub_name)
            prov.append(
                _prov(
                    "SPORT_EDITED",
                    f"message[{i}].{m.name}.sub_sport",
                    f"sub_sport {before!r} → {sub_name!r} (explicit user edit)",
                    {"before": before, "after": sub_name},
                )
            )
        out.append(new)
    return out, prov, warns


def _edit_device(
    messages: list[Message], manufacturer: str | int | None, product: str | int | None
) -> tuple[list[Message], list[ProvenanceEntry]]:
    """Rewrite the *recording* device identity only — file_id and the
    creator entry in device_info. Sensor entries are left alone."""
    prov: list[ProvenanceEntry] = []
    man_raw = _enum_raw("manufacturer", manufacturer) if manufacturer is not None else None
    man_name = ENUMS.get("manufacturer", {}).get(man_raw, man_raw) if man_raw is not None else None
    prod_raw = product if isinstance(product, int) else None
    if product is not None and prod_raw is None:
        raise EditError(
            "UNKNOWN_ENUM_NAME",
            f"product {product!r} must be a number (products are vendor-specific)",
            suggestion="pass the numeric product id, e.g. 2480",
        )

    out: list[Message] = []
    for i, m in enumerate(messages):
        new = m
        is_file_id = m.name == "file_id"
        is_creator = (
            m.name == "device_info"
            and m.fields.get("device_index", None) is not None
            and m.fields["device_index"].value == CREATOR_DEVICE_INDEX
        )
        if not (is_file_id or is_creator):
            out.append(new)
            continue
        for fname, raw, val in (
            ("manufacturer", man_raw, man_name),
            ("product", prod_raw, prod_raw),
        ):
            if raw is None or fname not in m.fields:
                continue
            before = m.fields[fname].value
            new = _set(new, fname, raw, val)
            prov.append(
                _prov(
                    "DEVICE_EDITED",
                    f"message[{i}].{m.name}.{fname}",
                    f"{fname} {before!r} → {val!r} (explicit user edit)",
                    {"before": before, "after": val},
                )
            )
        out.append(new)
    return out, prov


def _shift_time(
    messages: list[Message], seconds: int
) -> tuple[list[Message], list[ProvenanceEntry]]:
    """Shift every profile-typed timestamp, preserving relative spacing.

    Unknown fields are not shifted: chiptime cannot know an unrecognized
    field is a timestamp, and guessing would corrupt data (contract #6/#8).
    """
    out: list[Message] = []
    shifted = 0
    for m in messages:
        kinds = _field_kinds(m.global_num)
        new = m
        for fname, fv in m.fields.items():
            kind = kinds.get(fname)
            if kind not in ("date_time", "local_date_time"):
                continue
            if not isinstance(fv.raw, int) or isinstance(fv.raw, bool):
                continue
            moved = fv.raw + seconds
            if moved < TS_MIN or moved > TS_MAX:
                raise EditError(
                    "TIME_SHIFT_OUT_OF_RANGE",
                    (
                        f"shifting {m.name}.{fname} by {seconds}s would move it to {moved}, "
                        f"outside the representable FIT range [{TS_MIN}, {TS_MAX}]"
                    ),
                    suggestion="use a smaller offset; no bytes were written",
                )
            iso = fit_ts_to_iso(moved) if kind == "date_time" else fit_ts_to_iso_local(moved)
            new = _set(new, fname, moved, iso)
            shifted += 1
        out.append(new)
    prov = [
        _prov(
            "TIMESTAMPS_SHIFTED",
            "file",
            f"shifted {shifted} timestamp fields by {seconds}s (relative spacing preserved)",
            {"seconds": seconds, "fields_shifted": shifted},
        )
    ]
    return out, prov


# Fields that must scale together with distance, or the file contradicts
# itself: a speed stream that integrates to a different distance is exactly
# the kind of lie the trim work exists to prevent.
_DISTANCE_FIELDS = ("distance", "total_distance")
_SPEED_FIELDS = (
    "speed",
    "enhanced_speed",
    "avg_speed",
    "max_speed",
    "enhanced_avg_speed",
    "enhanced_max_speed",
)


def _wire_base_types(msg: Message) -> dict[str, int]:
    """field name → wire base type code, for bounds checking before we write."""
    mdef = MESSAGES.get(msg.global_num)
    if mdef is None or msg.wire is None:
        return {}
    num_to_name = {n: f.name for n, f in mdef.fields.items()}
    return {num_to_name[ws.num]: ws.base_type for ws in msg.wire.fields if ws.num in num_to_name}


def _fits(raw: float, base_type: int) -> bool:
    """Would this value survive the wire type it has to be written into?"""
    bt = BASE_TYPES.get(base_type)
    if bt is None or bt.invalid is None or bt.struct_code is None:
        return True
    if bt.name.startswith("float"):
        return True
    if bt.name.startswith(("uint", "enum", "byte")):
        return 0 <= raw < bt.invalid  # the invalid pattern is not a usable value
    limit = bt.invalid  # signed types: invalid is the positive limit
    return -limit <= raw <= limit


def _rescale_distance(
    messages: list[Message], target_m: float, current_m: float
) -> tuple[list[Message], list[ProvenanceEntry]]:
    """Scale recorded distance to a user-supplied total, taking speed with it."""
    if current_m <= 0:
        raise EditError(
            "DISTANCE_NOT_MEASURED",
            "this file records no distance to rescale",
            suggestion="check `chiptime parse` output; no bytes were written",
        )
    factor = target_m / current_m
    out: list[Message] = []
    touched = 0
    for m in messages:
        new = m
        wire_types = _wire_base_types(m)
        for fname in (*_DISTANCE_FIELDS, *_SPEED_FIELDS):
            fv = new.fields.get(fname)
            if fv is None or not isinstance(fv.raw, (int, float)) or isinstance(fv.raw, bool):
                continue
            scaled_raw = (
                type(fv.raw)(round(fv.raw * factor))
                if isinstance(fv.raw, int)
                else (fv.raw * factor)
            )
            base_type = wire_types.get(fname)
            if base_type is not None and not _fits(scaled_raw, base_type):
                raise EditError(
                    "DISTANCE_SCALE_OUT_OF_RANGE",
                    (
                        f"scaling by {factor:.3f} would push {m.name}.{fname} to "
                        f"{scaled_raw}, which does not fit its wire type"
                    ),
                    suggestion=(
                        "the requested distance is too far from the recorded one; "
                        "no bytes were written"
                    ),
                )
            value = fv.value * factor if isinstance(fv.value, (int, float)) else fv.value
            new = _set(new, fname, scaled_raw, value)
            touched += 1
        out.append(new)
    prov = [
        _prov(
            "DISTANCE_RESCALED",
            "file",
            f"distance rescaled {current_m:.0f}m → {target_m:.0f}m (factor {factor:.4f}); "
            f"speed scaled identically across {touched} field(s)",
            {"factor": factor, "from_m": current_m, "to_m": target_m, "fields": touched},
        )
    ]
    return out, prov


def edit(
    src: Source,
    *,
    sport: str | int | None = None,
    sub_sport: str | int | None = None,
    manufacturer: str | int | None = None,
    product: int | None = None,
    time_shift_s: int | None = None,
    total_distance_m: float | None = None,
    mode: Mode = "lenient",
) -> EditResult:
    """Change what a file *says about itself*, then prove it still parses.

    Only the named edits are applied; every other message, field, developer
    field, and unknown value round-trips untouched. Each edit is recorded in
    `provenance[]`, and the output is re-parsed in strict mode
    (`output_strict_ok`).

    Args:
        src: Path, bytes, or binary file object.
        sport: New sport, by profile name (``"running"``) or raw number.
        sub_sport: New sub-sport; never inferred from `sport`.
        manufacturer: New recording-device manufacturer, name or number.
        product: New product id (numeric — products are vendor-specific).
        time_shift_s: Signed seconds added to every profile-typed timestamp.
        total_distance_m: Set the activity's true distance (treadmill
            calibration). Records and speed are scaled by the same factor so
            the stream and the summaries still agree.
        mode: Parse policy for reading the input. ``strict`` refuses to edit
            a file that does not parse strictly — editing implies you
            believe the file is sound; use `repair` first if it is not.

    Returns:
        `EditResult` with the new bytes, provenance, warnings, and the
        strict-mode self-check verdict.

    Raises:
        EditError: no edit was requested, an enum name is unknown, or a
            time shift would leave the representable range. No bytes are
            written in any of these cases.
    """
    if all(
        v is None for v in (sport, sub_sport, manufacturer, product, time_shift_s, total_distance_m)
    ):
        raise EditError(
            "NO_EDIT_REQUESTED",
            "edit() was called without any edit to perform",
            suggestion=(
                "pass sport=, sub_sport=, manufacturer=, product=, time_shift_s=, "
                "or total_distance_m="
            ),
        )

    parsed = chiptime.parse(src, mode=mode)
    messages = list(parsed.messages)
    provenance: list[ProvenanceEntry] = []
    warnings: list[Diagnostic] = []

    if sport is not None or sub_sport is not None:
        messages, prov, warns = _edit_sport(messages, sport, sub_sport)
        provenance += prov
        warnings += warns
    if manufacturer is not None or product is not None:
        messages, prov = _edit_device(messages, manufacturer, product)
        provenance += prov
    if time_shift_s:
        messages, prov = _shift_time(messages, time_shift_s)
        provenance += prov
    if total_distance_m is not None:
        activity = parsed.activity
        current = None
        if activity and activity.sessions:
            session = activity.sessions[0]
            current = session.derived.distance_m or (
                session.declared.distance_m if session.declared else None
            )
        messages, prov = _rescale_distance(messages, total_distance_m, current or 0.0)
        provenance += prov

    data = encode_messages([encodable_from_message(m) for m in messages])
    try:
        chiptime.parse(data, mode="strict")
        strict_ok = True
    except FitError:
        strict_ok = False
    return EditResult(
        data=data,
        provenance=provenance,
        warnings=warnings,
        output_strict_ok=strict_ok,
        parse_result=parsed,
    )
