#!/usr/bin/env python3
"""Transcode chiptime's merged profile tables into TypeScript (F32, ADR-0009 s8).

Run from repo root:  uv run --project python python scripts/gen_profile_ts.py
CI regenerates and fails on any diff, so a maintainer who reruns
generate_profile.py against a newer SDK and forgets this step fails CI rather than
shipping two profiles.

Reads the *merged* tables (chiptime.profile.MESSAGES / ENUMS): generated SDK breadth
with the hand-authored, fitdecode-verified core applied on top. The merge policy
therefore stays in one language; TypeScript consumes its output.

Deterministic: sorted keys, no wall clock, floats via repr (shortest round-trip, so
JavaScript parses each one back to the identical double).
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "python" / "src"))

from chiptime.profile import ENUMS, GENERATED_SDK_VERSION, MESSAGES  # isort:skip
from chiptime.profile.core import SEMICIRCLE_SCALE  # isort:skip

OUT = pathlib.Path(__file__).resolve().parents[1] / "js" / "src" / "profile" / "generated.ts"

HEADER = f"""/**
 * GENERATED FILE -- do not edit. Regenerate with:
 *
 *     uv run --project python python scripts/gen_profile_ts.py
 *
 * Source: chiptime's **merged** profile tables -- the Global FIT Profile (SDK version
 * {GENERATED_SDK_VERSION}) providing breadth, with chiptime's hand-authored,
 * fitdecode-verified core applied on top, field by field and enum value by enum
 * value. This file is therefore SDK-version-plus-core, not the SDK profile: see
 * `python/src/chiptime/profile/__init__.py` for the merge policy and
 * `python/src/chiptime/profile/core.py` for the verified entries.
 *
 * These are functional interface facts (message numbers, field numbers, scales,
 * units) expressed in chiptime's own data shapes and licensed under chiptime's MIT
 * license (ADR-0004). chiptime is not affiliated with or endorsed by Garmin. FIT and
 * Garmin are trademarks of Garmin Ltd. No Garmin SDK file is included in this
 * repository.
 *
 * INVARIANT: nothing may depend on the iteration order of these tables. They are
 * plain lookup objects, and integer-like keys are reordered by the runtime. Code
 * needing a stable order must sort the keys explicitly (ADR-0009 section 8).
 */

import type {{ MessageDef }} from "./core.js";

export const GENERATED_SDK_VERSION = {json.dumps(GENERATED_SDK_VERSION)};

/** Semicircles to degrees; the same expression `core.py` uses (taxonomy #27). */
const S = 2 ** 31 / 180.0;
"""


def num(value: float) -> str:
    """Emit a float so JavaScript parses back the identical double.

    repr is shortest-round-trip in CPython and JavaScript's parser is correctly
    rounded, which is the same equivalence F31 settled by vectors. It matters: the
    profile carries scales like 0.7111111, 28.57143 and 11930464.711111112, and a
    scale off by one ULP silently mis-scales every value in its field.
    """
    if value == SEMICIRCLE_SCALE:
        return "S"  # keep the constant visible as an expression, as Python does
    if value == int(value) and abs(value) < 2**53:
        return str(int(value))
    return repr(float(value))


def field_literal(f: object) -> str:
    num_ = f.num  # type: ignore[attr-defined]
    return (
        f"{num_}:{{num:{num_},name:{json.dumps(f.name)},"  # type: ignore[attr-defined]
        f"kind:{json.dumps(f.kind)},"  # type: ignore[attr-defined]
        f"scale:{num(f.scale)},offset:{num(f.offset)},"  # type: ignore[attr-defined]
        f"units:{json.dumps(f.units) if f.units is not None else 'null'}}}"  # type: ignore[attr-defined]
    )


def emit_messages() -> str:
    lines = ["", "export const GENERATED_MESSAGES: Readonly<Record<number, MessageDef>> = {"]
    for msg_num in sorted(MESSAGES):
        m = MESSAGES[msg_num]
        fields = ",".join(field_literal(m.fields[fn]) for fn in sorted(m.fields))
        lines.append(f"  {msg_num}: {{ num: {msg_num}, name: {json.dumps(m.name)}, fields: {{")
        lines.append(f"    {fields}")
        lines.append("  } },")
    lines.append("};")
    return "\n".join(lines)


def emit_enums() -> str:
    decl = "Readonly<Record<string, Readonly<Record<number, string>>>>"
    lines = ["", f"export const GENERATED_ENUMS: {decl} = {{"]
    for name in sorted(ENUMS):
        values = ENUMS[name]
        body = ",".join(f"{v}:{json.dumps(values[v])}" for v in sorted(values))
        lines.append(f"  {json.dumps(name)}: {{ {body} }},")
    lines.append("};")
    return "\n".join(lines)


def main() -> None:
    # Field shapes are structurally implied by `MessageDef["fields"]`, so only
    # `MessageDef` needs importing; the literals below type-check against it.
    body = HEADER + emit_messages() + "\n" + emit_enums() + "\n"
    OUT.write_text(body, encoding="utf-8")
    print(f"wrote {OUT.relative_to(pathlib.Path.cwd())} ({len(body):,} bytes)")


if __name__ == "__main__":
    main()
