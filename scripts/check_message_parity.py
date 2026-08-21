#!/usr/bin/env python3
"""Message-level parity across every corpus case (F34).

Run from repo root:  uv run --project python python scripts/check_message_parity.py

Drives a Decoder DIRECTLY rather than going through iter_messages (F34 critique,
amendment C2). iter_messages yields messages and never calls finish(), so
diagnostics and provenance are unreachable through it -- a gate built on it would
have compared nothing on exactly the outputs contract #1 governs, and reported
success.

Three streams are compared, each under its own ordering rule:
  messages     in file order, every field's value / raw / units / developer origin
  diagnostics  in production order
  provenance   salvage entries sorted by (definition offset, field number, reason)

Serialized with each side's own canonical JSON (F31), so the comparison inherits a
contract already proven byte-identical across processes and languages.

Exit 0 = every case agrees.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python" / "src"))

from chiptime import iter_frames  # isort:skip
from chiptime.canonical import dumps  # isort:skip
from chiptime.decode import Decoder  # isort:skip
from chiptime.frames import DataFrame  # isort:skip

MAX_SAFE = 2**53 - 1


def jsonable(v: object) -> object:
    """Values as a canonical-JSON tree, matching the TypeScript dumper field for field."""
    if isinstance(v, bytes):
        return {"__bytes__": v.hex()}
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, int) and abs(v) > MAX_SAFE:
        return {"__big__": str(v)}
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        return {"__nonfinite__": repr(v)}
    if isinstance(v, (list, tuple)):
        return [jsonable(x) for x in v]
    return v


def dump_case(data: bytes) -> object:
    dec = Decoder()
    for ev in iter_frames(data):
        if isinstance(ev, DataFrame):
            dec.decode(ev)
    out = dec.finish()
    return {
        "messages": [
            {
                "global_num": m.global_num,
                "name": m.name,
                "local_id": m.local_id,
                "byte_offset": m.byte_offset,
                "fields": [
                    [
                        fname,
                        jsonable(fval.value),
                        jsonable(fval.raw),
                        fval.units,
                        None
                        if fval.developer is None
                        else [
                            fval.developer.developer_data_index,
                            fval.developer.field_definition_number,
                            fval.developer.application_id,
                            fval.developer.vendor,
                            fval.developer.canonical_name,
                        ],
                    ]
                    for fname, fval in m.fields.items()
                ],
            }
            for m in out.messages
        ],
        "diagnostics": [[d.code, d.detail, d.scope] for d in out.diagnostics],
        "provenance": [
            [p.code, p.action, p.scope, p.detail, p.byte_offset, jsonable(p.data)]
            for p in out.provenance
        ],
        "defects": [[d.code, d.detail, d.offset, d.severity] for d in out.defects],
    }


DUMP_JS = """
import { readFileSync } from "node:fs";
import { iterFrames } from "./api.js";
import { canonicalDump } from "./_msgdump.js";
process.stdout.write(JSON.stringify(canonicalDump(JSON.parse(process.argv[2]))));
"""

HELPER_JS = """
import { readFileSync } from "node:fs";
import { iterFrames } from "./api.js";
import { Decoder } from "./decode.js";
import { dumps } from "./canonical.js";

const MAX_SAFE = Number.MAX_SAFE_INTEGER;
const decoder = new TextDecoder();

function hex(u8) {
  let s = "";
  for (const b of u8) s += b.toString(16).padStart(2, "0");
  return s;
}

function jsonable(v) {
  if (v instanceof Uint8Array) return { __bytes__: hex(v) };
  if (v === null || typeof v === "boolean") return v;
  if (typeof v === "bigint") {
    return (v > BigInt(MAX_SAFE) || v < BigInt(-MAX_SAFE)) ? { __big__: v.toString() } : Number(v);
  }
  if (typeof v === "number" && !Number.isFinite(v)) {
    return { __nonfinite__: Number.isNaN(v) ? "nan" : (v > 0 ? "inf" : "-inf") };
  }
  if (Array.isArray(v)) return v.map(jsonable);
  return v;
}

export function canonicalDump(cases) {
  const out = {};
  for (const [name, path] of cases) {
    const dec = new Decoder();
    for (const ev of iterFrames(new Uint8Array(readFileSync(path)))) {
      if (ev.kind === "data") dec.decode(ev);
    }
    const o = dec.finish();
    const tree = {
      messages: o.messages.map((m) => ({
        global_num: m.globalNum,
        name: m.name,
        local_id: m.localId,
        byte_offset: m.byteOffset,
        fields: [...m.fields.entries()].map(([fname, fval]) => [
          fname,
          jsonable(fval.value),
          jsonable(fval.raw),
          fval.units,
          fval.developer === null ? null : [
            fval.developer.developerDataIndex,
            fval.developer.fieldDefinitionNumber,
            fval.developer.applicationId,
            fval.developer.vendor,
            fval.developer.canonicalName,
          ],
        ]),
      })),
      diagnostics: o.diagnostics.map((d) => [d.code, d.detail, d.scope]),
      provenance: o.provenance.map((p) => [
        p.code, p.action, p.scope, p.detail, p.byteOffset, jsonable(p.data),
      ]),
      defects: o.defects.map((d) => [d.code, d.detail, d.offset, d.severity]),
    };
    out[name] = decoder.decode(dumps(tree));
  }
  return out;
}
"""


def typescript_side(cases: list[tuple[str, pathlib.Path]]) -> dict[str, str]:
    js_dir = ROOT / "js"
    if not (js_dir / "node_modules").exists():
        raise SystemExit("js/node_modules missing -- run `npm install` in js/ first")
    subprocess.run(["npm", "run", "build"], cwd=js_dir, check=True, capture_output=True)
    helper = js_dir / "dist" / "esm" / "_msgdump.js"
    runner = js_dir / "dist" / "esm" / "_msgrun.mjs"
    helper.write_text(HELPER_JS, encoding="utf-8")
    runner.write_text(DUMP_JS, encoding="utf-8")
    payload = json.dumps([[n, str(p)] for n, p in cases])
    try:
        res = subprocess.run(
            ["node", str(runner), payload], cwd=js_dir, capture_output=True, text=True
        )
    finally:
        helper.unlink(missing_ok=True)
        runner.unlink(missing_ok=True)
    if res.returncode != 0:
        raise SystemExit(f"dumping the TypeScript messages failed:\n{res.stderr.strip()}")
    return json.loads(res.stdout)


def first_difference(a: str, b: str) -> str:
    for i, (ca, cb) in enumerate(zip(a, b, strict=False)):
        if ca != cb:
            lo = max(0, i - 70)
            return (
                f"at char {i}:\n      python:     ...{a[lo : i + 70]}"
                f"\n      typescript: ...{b[lo : i + 70]}"
            )
    return f"one is a prefix of the other (python {len(a)}, typescript {len(b)})"


def main() -> None:
    corpus = ROOT / "corpus" / "cases"
    cases = sorted(
        (f"{p.parent.parent.name}/{p.parent.name}", p) for p in corpus.glob("*/*/input.fit")
    )
    if not cases:
        raise SystemExit("no corpus cases found")

    py = {name: dumps(dump_case(path.read_bytes())).decode("utf-8") for name, path in cases}
    ts = typescript_side(cases)

    failures = [(n, first_difference(py[n], ts.get(n, ""))) for n, _ in cases if py[n] != ts.get(n)]
    if failures:
        print(f"message parity: {len(failures)} of {len(cases)} case(s) diverged")
        for name, where in failures[:5]:
            print(f"\n  {name}\n    {where}")
        if len(failures) > 5:
            print(f"\n  ... and {len(failures) - 5} more: {[n for n, _ in failures[5:]]}")
        raise SystemExit(1)

    totals = [json.loads(py[n]) for n, _ in cases]
    n_msg = sum(len(t["messages"]) for t in totals)
    n_diag = sum(len(t["diagnostics"]) for t in totals)
    n_prov = sum(len(t["provenance"]) for t in totals)
    print(
        f"message parity: ok -- {len(cases)} cases, {n_msg} messages, "
        f"{n_diag} diagnostics, {n_prov} provenance entries identical"
    )


if __name__ == "__main__":
    main()
