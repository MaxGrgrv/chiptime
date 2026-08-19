"""Known-vendor developer-field registry (taxonomy #22d).

Vendor identity comes from developer_data_id.manufacturer_id (stable across
app builds, unlike application UUIDs). A (vendor, normalized field name) match
promotes the field to a canonical stream name for the semantic layer.
Data-only; growing this table is an M4 workstream.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VendorField:
    canonical_name: str
    units: str | None = None


# key: (manufacturer enum name, field_description.field_name lowercased/stripped)
KNOWN_VENDOR_FIELDS: dict[tuple[str, str], VendorField] = {
    ("stryd", "power"): VendorField("running_power", "W"),
    ("stryd", "leg spring stiffness"): VendorField("leg_spring_stiffness", "kN/m"),
    ("stryd", "form power"): VendorField("form_power", "W"),
    ("stryd", "air power"): VendorField("air_power", "W"),
    ("greenteg", "core temperature"): VendorField("core_temperature", "C"),
    ("greenteg", "skin temperature"): VendorField("skin_temperature", "C"),
    ("moxy", "smo2"): VendorField("smo2", "percent"),
    ("moxy", "thb"): VendorField("thb", "g/dl"),
}


def lookup(vendor: str | None, field_name: str | None) -> VendorField | None:
    if vendor is None or field_name is None:
        return None
    return KNOWN_VENDOR_FIELDS.get((vendor, field_name.strip().lower()))
