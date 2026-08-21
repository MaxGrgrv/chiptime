#!/usr/bin/env python3
"""Value-level parity between the Python and TypeScript profile tables (F32).

Run from repo root:  uv run --project python python scripts/check_profile_parity.py

This is NOT the same gate as CI's regenerate-and-diff, and neither substitutes for
the other:

  regenerate-and-diff  catches *staleness* -- generated.ts not rebuilt after the
                       Python tables changed.
  this script          catches *transcoding faults* -- a truncated bigint, a float
                       that lost a digit, a mis-escaped label. A transcoder that has
                       always been wrong the same way passes the diff forever.

It loads the TypeScript values through node and compares them to the Python values,
so it compares what the runtime sees rather than what the source says.

Exit 0 = every message, field, enum name, enum value and label agrees.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python" / "src"))

from chiptime.profile import ENUMS, GENERATED_SDK_VERSION, MESSAGES  # isort:skip

DUMP_JS = """
import { MESSAGES, ENUMS, GENERATED_SDK_VERSION } from "./profile/index.js";
const messages = {};
for (const [num, m] of Object.entries(MESSAGES)) {
  const fields = {};
  for (const [fnum, f] of Object.entries(m.fields)) {
    fields[fnum] = [f.num, f.name, f.kind, f.scale, f.offset, f.units];
  }
  messages[num] = [m.num, m.name, fields];
}
const enums = {};
for (const [name, values] of Object.entries(ENUMS)) enums[name] = { ...values };
process.stdout.write(JSON.stringify({ messages, enums, sdk: GENERATED_SDK_VERSION }));
"""


def python_side() -> dict[str, object]:
    messages = {}
    for num, m in MESSAGES.items():
        fields = {
            str(fnum): [f.num, f.name, f.kind, f.scale, f.offset, f.units]
            for fnum, f in m.fields.items()
        }
        messages[str(num)] = [m.num, m.name, fields]
    enums = {name: {str(v): label for v, label in values.items()} for name, values in ENUMS.items()}
    return {"messages": messages, "enums": enums, "sdk": GENERATED_SDK_VERSION}


def typescript_side() -> dict[str, object]:
    js_dir = ROOT / "js"
    if not (js_dir / "node_modules").exists():
        raise SystemExit("js/node_modules missing -- run `npm install` in js/ first")
    subprocess.run(["npm", "run", "build"], cwd=js_dir, check=True, capture_output=True)
    dump = js_dir / "dist" / "esm" / "_parity_dump.mjs"
    dump.write_text(DUMP_JS, encoding="utf-8")
    try:
        out = subprocess.run(["node", str(dump)], cwd=js_dir, capture_output=True, text=True)
    finally:
        dump.unlink(missing_ok=True)
    if out.returncode != 0:
        raise SystemExit(f"dumping the TypeScript tables failed:\n{out.stderr.strip()}")
    return json.loads(out.stdout)


def diff(py: dict[str, object], ts: dict[str, object]) -> list[str]:
    problems: list[str] = []
    if py["sdk"] != ts["sdk"]:
        problems.append(f"SDK version: python={py['sdk']!r} typescript={ts['sdk']!r}")

    pm, tm = py["messages"], ts["messages"]  # type: ignore[index]
    for num in sorted(set(pm) | set(tm), key=int):
        if num not in tm:
            problems.append(f"message {num} ({pm[num][1]}) missing from TypeScript")
            continue
        if num not in pm:
            problems.append(f"message {num} ({tm[num][1]}) present only in TypeScript")
            continue
        p_num, p_name, p_fields = pm[num]
        t_num, t_name, t_fields = tm[num]
        if (p_num, p_name) != (t_num, t_name):
            problems.append(
                f"message {num}: python=({p_num},{p_name}) typescript=({t_num},{t_name})"
            )
        for fnum in sorted(set(p_fields) | set(t_fields), key=int):
            pf, tf = p_fields.get(fnum), t_fields.get(fnum)
            if pf != tf:
                problems.append(
                    f"message {num} ({p_name}) field {fnum}: python={pf} typescript={tf}"
                )

    pe, te = py["enums"], ts["enums"]  # type: ignore[index]
    for name in sorted(set(pe) | set(te)):
        pv, tv = pe.get(name), te.get(name)
        if pv is None or tv is None:
            problems.append(
                f"enum {name!r}: {'missing from TypeScript' if tv is None else 'TypeScript only'}"
            )
            continue
        for value in sorted(set(pv) | set(tv), key=int):
            if pv.get(value) != tv.get(value):
                problems.append(
                    f"enum {name!r} value {value}: "
                    f"python={pv.get(value)!r} typescript={tv.get(value)!r}"
                )
    return problems


def main() -> None:
    py = python_side()
    ts = typescript_side()
    problems = diff(py, ts)
    n_msg = len(py["messages"])  # type: ignore[arg-type]
    n_enum = len(py["enums"])  # type: ignore[arg-type]
    if problems:
        print(f"profile parity: {len(problems)} divergence(s)")
        for p in problems[:40]:
            print(f"  {p}")
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")
        raise SystemExit(1)
    n_fields = sum(len(m[2]) for m in py["messages"].values())  # type: ignore[union-attr]
    n_values = sum(len(v) for v in py["enums"].values())  # type: ignore[union-attr]
    print(
        f"profile parity: ok -- {n_msg} messages ({n_fields} fields), "
        f"{n_enum} enums ({n_values} values), SDK {py['sdk']}"
    )


if __name__ == "__main__":
    main()
