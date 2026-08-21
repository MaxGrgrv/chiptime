#!/usr/bin/env python3
"""Frame-level parity across every corpus case (F33).

Run from repo root:  uv run --project python python scripts/check_frame_parity.py

The first gate where TypeScript consumes the corpus. Both implementations read every
corpus/cases/*/input.fit through their frame reader, each serializes the event
stream with its OWN canonical JSON (F31), and the two byte strings must match.

Using canonical JSON rather than an ad-hoc diff format is deliberate: the comparison
inherits a contract already proven byte-identical across processes and languages,
instead of inventing a second notion of "the same".

ALL 72 cases are in scope, including the five that exercise frame-level resync.
read_stream performs resync itself -- what the later feature adds is the API-level
mode policy, which iter_frames never participates in. Scoping this gate to
"cases that decode cleanly" would have excluded exactly the cases where the resync
scanner is the code under test (F33 critique, Finding 1).

Exit 0 = every case produces identical frame events.
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
from chiptime.errors import Defect  # isort:skip
from chiptime.frames import (  # isort:skip
    CrcFrame,
    DataFrame,
    DefinitionFrame,
    EndOfStream,
    FileHeader,
    SkippedBytes,
)

# The five cases whose resync path this gate exists to cover. Named so a change that
# stops exercising them is visible rather than silent.
RESYNC_CASES = {
    "container/zip-wrapped",
    "protocol/frame-shift-insert",
    "structural/garbage-block-midfile",
    "structural/preamble-garbage",
    "structural/undefined-local-resync",
}


def py_event(ev: object) -> dict[str, object]:
    """One frame event as a plain JSON tree. Field-for-field with the TS dumper."""
    if isinstance(ev, FileHeader):
        return {
            "kind": "header",
            "offset": ev.offset,
            "size": ev.size,
            "protocol_version": ev.protocol_version,
            "profile_version": ev.profile_version,
            "data_size": ev.data_size,
            "magic_ok": ev.magic_ok,
            "crc_declared": ev.crc_declared,
            "crc_ok": ev.crc_ok,
        }
    if isinstance(ev, DefinitionFrame):
        return {
            "kind": "definition",
            "offset": ev.offset,
            "local_id": ev.local_id,
            "global_num": ev.global_num,
            "big_endian": ev.big_endian,
            "fields": [[f.num, f.size, f.base_type] for f in ev.fields],
            "dev_fields": [[f.num, f.size, f.dev_data_index] for f in ev.dev_fields],
        }
    if isinstance(ev, DataFrame):
        return {
            "kind": "data",
            "offset": ev.offset,
            "local_id": ev.local_id,
            "definition_offset": ev.definition.offset,
            "payload": ev.payload.hex(),
            "time_offset": ev.time_offset,
        }
    if isinstance(ev, CrcFrame):
        return {
            "kind": "crc",
            "offset": ev.offset,
            "declared": ev.declared,
            "computed": ev.computed,
            "ok": ev.ok,
        }
    if isinstance(ev, SkippedBytes):
        return {"kind": "skipped", "offset": ev.offset, "length": ev.length, "reason": ev.reason}
    if isinstance(ev, Defect):
        return {
            "kind": "defect",
            "code": ev.code,
            "detail": ev.detail,
            "offset": ev.offset,
            "severity": ev.severity,
        }
    if isinstance(ev, EndOfStream):
        return {"kind": "eos", "consumed": ev.consumed}
    raise SystemExit(f"unhandled frame event type {type(ev).__name__}")


def python_side(cases: list[tuple[str, pathlib.Path]]) -> dict[str, str]:
    out = {}
    for name, path in cases:
        events = [py_event(e) for e in iter_frames(path.read_bytes())]
        out[name] = dumps(events).decode("utf-8")
    return out


def typescript_side(cases: list[tuple[str, pathlib.Path]]) -> dict[str, str]:
    js_dir = ROOT / "js"
    if not (js_dir / "node_modules").exists():
        raise SystemExit("js/node_modules missing -- run `npm install` in js/ first")
    subprocess.run(["npm", "run", "build"], cwd=js_dir, check=True, capture_output=True)
    script = js_dir / "dist" / "esm" / "_frame_dump.mjs"
    script.write_text(
        """
import { readFileSync } from "node:fs";
import { iterFrames } from "./api.js";
import { dumps } from "./canonical.js";

const cases = JSON.parse(process.argv[2]);
const decoder = new TextDecoder();
const out = {};
for (const [name, path] of cases) {
  const events = [];
  for (const ev of iterFrames(new Uint8Array(readFileSync(path)))) {
    switch (ev.kind) {
      case "header":
        events.push({ kind: "header", offset: ev.offset, size: ev.size,
          protocol_version: ev.protocolVersion, profile_version: ev.profileVersion,
          data_size: ev.dataSize, magic_ok: ev.magicOk,
          crc_declared: ev.crcDeclared, crc_ok: ev.crcOk });
        break;
      case "definition":
        events.push({ kind: "definition", offset: ev.offset, local_id: ev.localId,
          global_num: ev.globalNum, big_endian: ev.bigEndian,
          fields: ev.fields.map((f) => [f.num, f.size, f.baseType]),
          dev_fields: ev.devFields.map((f) => [f.num, f.size, f.devDataIndex]) });
        break;
      case "data":
        events.push({ kind: "data", offset: ev.offset, local_id: ev.localId,
          definition_offset: ev.definition.offset,
          payload: Array.from(ev.payload, (b) => b.toString(16).padStart(2, "0")).join(""),
          time_offset: ev.timeOffset });
        break;
      case "crc":
        events.push({ kind: "crc", offset: ev.offset, declared: ev.declared,
          computed: ev.computed, ok: ev.ok });
        break;
      case "skipped":
        events.push({ kind: "skipped", offset: ev.offset, length: ev.length, reason: ev.reason });
        break;
      case "defect":
        events.push({ kind: "defect", code: ev.code, detail: ev.detail,
          offset: ev.offset, severity: ev.severity });
        break;
      case "eos":
        events.push({ kind: "eos", consumed: ev.consumed });
        break;
      default:
        throw new Error(`unhandled frame event ${JSON.stringify(ev)}`);
    }
  }
  out[name] = decoder.decode(dumps(events));
}
process.stdout.write(JSON.stringify(out));
""",
        encoding="utf-8",
    )
    payload = json.dumps([[n, str(p)] for n, p in cases])
    try:
        res = subprocess.run(
            ["node", str(script), payload], cwd=js_dir, capture_output=True, text=True
        )
    finally:
        script.unlink(missing_ok=True)
    if res.returncode != 0:
        raise SystemExit(f"dumping the TypeScript frames failed:\n{res.stderr.strip()}")
    return json.loads(res.stdout)


def first_difference(a: str, b: str) -> str:
    for i, (ca, cb) in enumerate(zip(a, b, strict=False)):
        if ca != cb:
            lo = max(0, i - 60)
            return (
                f"at char {i}:\n    python:     ...{a[lo : i + 60]}"
                f"\n    typescript: ...{b[lo : i + 60]}"
            )
    return f"one is a prefix of the other (python {len(a)} chars, typescript {len(b)} chars)"


def main() -> None:
    corpus = ROOT / "corpus" / "cases"
    cases = sorted(
        (f"{p.parent.parent.name}/{p.parent.name}", p) for p in corpus.glob("*/*/input.fit")
    )
    if not cases:
        raise SystemExit("no corpus cases found")

    py = python_side(cases)
    ts = typescript_side(cases)

    missing = RESYNC_CASES - {n for n, _ in cases}
    if missing:
        raise SystemExit(f"named resync cases are absent from the corpus: {sorted(missing)}")

    failures = []
    for name, _ in cases:
        if py[name] != ts.get(name):
            failures.append((name, first_difference(py[name], ts.get(name, ""))))

    if failures:
        print(f"frame parity: {len(failures)} of {len(cases)} case(s) diverged")
        for name, where in failures[:6]:
            print(f"\n  {name}\n    {where}")
        if len(failures) > 6:
            print(f"\n  ... and {len(failures) - 6} more")
        raise SystemExit(1)

    events = sum(json.loads(py[n]).__len__() for n, _ in cases)
    print(
        f"frame parity: ok -- {len(cases)} cases, {events} frame events identical "
        f"(incl. {len(RESYNC_CASES)} resync cases)"
    )


if __name__ == "__main__":
    main()
