#!/usr/bin/env python3
"""Generate chiptime's full profile tables from a locally-downloaded FIT SDK.

Usage:
    python scripts/generate_profile.py ~/Downloads/FitSDKRelease_21.158.00.zip

Reads Profile.xlsx via stdlib only (zipfile + ElementTree). Writes
python/src/chiptime/profile/generated.py — OUR data shape under OUR license
(ADR-0004). The SDK zip and Profile.xlsx must NEVER be committed.

Deterministic: same input → identical output (sorted; no wall clock).
"""

from __future__ import annotations

import io
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
SEMICIRCLE_SCALE_EXPR = "2**31 / 180.0"


def load_sheets(src: Path) -> tuple[list[dict[str, str]], list[dict[str, str]], str]:
    raw = src.read_bytes()
    version = "unknown"
    m = re.search(r"(\d+\.\d+(?:\.\d+)?)", src.name)
    if m:
        version = m.group(1)
    if src.suffix.lower() == ".zip":
        outer = zipfile.ZipFile(io.BytesIO(raw))
        name = next(n for n in outer.namelist() if n.endswith("Profile.xlsx"))
        raw = outer.read(name)
    z = zipfile.ZipFile(io.BytesIO(raw))
    shared = ET.fromstring(z.read("xl/sharedStrings.xml"))
    strings = ["".join(t.text or "" for t in si.iter(NS + "t")) for si in shared]
    wb = z.read("xl/workbook.xml").decode()
    order = re.findall(r'name="([^"]+)"', wb)
    sheet_paths = sorted(
        n for n in z.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
    )
    named = dict(zip(order, sheet_paths, strict=False))

    def rows(path: str) -> list[dict[str, str]]:
        root = ET.fromstring(z.read(path))
        out = []
        for row in root.iter(NS + "row"):
            cells: dict[str, str] = {}
            for c in row.iter(NS + "c"):
                col = "".join(ch for ch in (c.get("r") or "") if ch.isalpha())
                v = c.find(NS + "v")
                if v is None or v.text is None:
                    continue
                cells[col] = strings[int(v.text)] if c.get("t") == "s" else v.text
            out.append(cells)
        return out

    return rows(named["Types"]), rows(named["Messages"]), version


def parse_types(rows: list[dict[str, str]]) -> dict[str, dict[int, str]]:
    enums: dict[str, dict[int, str]] = {}
    current: str | None = None
    for r in rows[1:]:
        if r.get("A"):
            current = r["A"]
            enums[current] = {}
        elif current and r.get("C") and r.get("D") is not None:
            try:
                enums[current][int(str(r["D"]), 0)] = r["C"]
            except ValueError:
                continue
    return {k: v for k, v in enums.items() if v}


def parse_messages(
    rows: list[dict[str, str]], mesg_num: dict[str, int], enums: dict[str, dict[int, str]]
) -> dict[int, list[tuple[int, str, str, float, float, str | None]]]:
    out: dict[int, list[tuple[int, str, str, float, float, str | None]]] = {}
    gnum: int | None = None
    for r in rows[1:]:
        if r.get("A"):
            gnum = mesg_num.get(r["A"])
            if gnum is not None:
                out[gnum] = []
            continue
        if gnum is None or gnum not in out:
            continue
        if not r.get("B") or not r.get("C"):
            continue  # subfield row (dynamic resolution stays curated) or blank
        try:
            fnum = int(str(r["B"]), 0)
        except ValueError:
            continue
        ftype = r.get("D", "")
        name = r["C"]
        units = r.get("I") or None

        def scalar(v: str | None, default: float) -> float:
            if not v or "," in v:  # component multi-scale: keep raw
                return default
            try:
                return float(v)
            except ValueError:
                return default

        scale = scalar(r.get("G"), 1.0)
        offset = scalar(r.get("H"), 0.0)

        if ftype in ("date_time", "local_date_time"):
            kind = ftype
        elif ftype == "string":
            kind = "string"
        elif ftype == "byte":
            kind = "bytes"
        elif ftype in enums:
            kind = f"enum:{ftype}"
        else:
            kind = "number"

        if units == "semicircles":  # core's documented divergence, applied globally
            kind, scale, offset, units = "number", -1.0, 0.0, "deg"  # -1 marks semicircle
        out[gnum].append((fnum, name, kind, scale, offset, units))
    return out


def main() -> int:
    src = Path(sys.argv[1]).expanduser()
    types_rows, msg_rows, version = load_sheets(src)
    enums = parse_types(types_rows)
    mesg_num = {name: num for num, name in enums.get("mesg_num", {}).items()}
    messages = parse_messages(msg_rows, mesg_num, enums)
    num_to_name = enums.get("mesg_num", {})

    # base types are wire machinery, not profile enums
    for bt in ("fit_base_type",):
        enums.pop(bt, None)

    lines = [
        '"""GENERATED FILE — do not edit. Regenerate with:',
        "",
        "    python scripts/generate_profile.py <FitSDKRelease zip>",
        "",
        f"Source: Global FIT Profile, SDK version {version}.",
        "This file contains functional interface facts (message numbers, field",
        "numbers, scales, units) expressed in chiptime's own data shapes and",
        "licensed under chiptime's MIT license (ADR-0004). chiptime is not",
        "affiliated with or endorsed by Garmin. FIT and Garmin are trademarks",
        "of Garmin Ltd. No Garmin SDK file is included in this repository.",
        '"""',
        "",
        "from chiptime.profile.core import FieldDef, MessageDef",
        "",
        f'GENERATED_SDK_VERSION = "{version}"',
        "",
        "_S = 2**31 / 180.0  # semicircles -> degrees",
        "",
        "GENERATED_MESSAGES: dict[int, MessageDef] = {",
    ]
    for gnum in sorted(messages):
        name = num_to_name.get(gnum, f"unknown_{gnum}")
        fields = sorted(messages[gnum])
        lines.append(f"    {gnum}: MessageDef({gnum}, {name!r}, {{")
        for fnum, fname, kind, scale, offset, units in fields:
            scale_expr = "_S" if scale == -1.0 else repr(scale)
            lines.append(
                f"        {fnum}: FieldDef({fnum}, {fname!r}, {kind!r},"
                f" {scale_expr}, {offset!r}, {units!r}),"
            )
        lines.append("    }),")
    lines.append("}")
    lines.append("")
    lines.append("GENERATED_ENUMS: dict[str, dict[int, str]] = {")
    for ename in sorted(enums):
        lines.append(f"    {ename!r}: {{")
        for val in sorted(enums[ename]):
            lines.append(f"        {val}: {enums[ename][val]!r},")
        lines.append("    },")
    lines.append("}")

    out = Path(__file__).resolve().parents[1] / "python/src/chiptime/profile/generated.py"
    out.write_text("\n".join(lines) + "\n")
    n_fields = sum(len(v) for v in messages.values())
    n_enum_vals = sum(len(v) for v in enums.values())
    print(f"wrote {out}")
    print(
        f"  {len(messages)} messages / {n_fields} fields /"
        f" {len(enums)} enums ({n_enum_vals} values) — SDK {version}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
