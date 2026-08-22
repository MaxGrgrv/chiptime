#!/usr/bin/env python3
"""parse() parity across every corpus case (F35, closed out at F36).

Run from repo root:  uv run --project python python scripts/check_parse_parity.py

Every one of the 72 cases is compared against its COMMITTED expected.json, byte for
byte, in lenient mode -- TypeScript producing the corpus snapshot. Strict and
forensic are compared implementation to implementation, and every case is parsed
twice to prove determinism.

The two-tier scheme this script carried at F35 is gone. It existed only because the
semantic model did not, and a scaffold that outlives its reason becomes a place
where coverage can quietly narrow again -- while still passing.

Exit 0 = every case agrees.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python" / "src"))

import chiptime  # isort:skip
from chiptime.canonical import dumps  # isort:skip

MODES = ("lenient", "strict", "forensic")

RUNNER_JS = """
import { readFileSync } from "node:fs";
import { parse } from "./api.js";
import { dumps } from "./canonical.js";

const decoder = new TextDecoder();
const cases = JSON.parse(process.argv[2]);
const out = {};
for (const [name, path, mode] of cases) {
  const data = new Uint8Array(readFileSync(path));
  try {
    const r = parse(data, { mode });
    out[`${name}::${mode}`] = { ok: true, json: decoder.decode(r.toCanonicalJson()) };
  } catch (e) {
    out[`${name}::${mode}`] = { ok: false, code: e.code ?? String(e), name: e.name ?? "Error" };
  }
}
process.stdout.write(JSON.stringify(out));
"""


def python_side(cases: list[tuple[str, pathlib.Path]]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for name, path in cases:
        data = path.read_bytes()
        for mode in MODES:
            key = f"{name}::{mode}"
            try:
                r = chiptime.parse(data, mode=mode)
                out[key] = {"ok": True, "json": dumps(r.to_dict()).decode("utf-8")}
            except chiptime.FitError as exc:
                out[key] = {"ok": False, "code": exc.code, "name": type(exc).__name__}
    return out


def typescript_side(cases: list[tuple[str, pathlib.Path]]) -> dict[str, dict]:
    js_dir = ROOT / "js"
    if not (js_dir / "node_modules").exists():
        raise SystemExit("js/node_modules missing -- run `npm install` in js/ first")
    subprocess.run(["npm", "run", "build"], cwd=js_dir, check=True, capture_output=True)
    runner = js_dir / "dist" / "esm" / "_parserun.mjs"
    runner.write_text(RUNNER_JS, encoding="utf-8")
    payload = json.dumps([[n, str(p), m] for n, p in cases for m in MODES])
    try:
        res = subprocess.run(
            ["node", str(runner), payload], cwd=js_dir, capture_output=True, text=True
        )
    finally:
        runner.unlink(missing_ok=True)
    if res.returncode != 0:
        raise SystemExit(f"running the TypeScript parser failed:\n{res.stderr.strip()}")
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

    py = python_side(cases)
    ts = typescript_side(cases)

    failures: list[tuple[str, str]] = []
    snapshot_failures: list[tuple[str, str]] = []

    for name, path in cases:
        for mode in MODES:
            key = f"{name}::{mode}"
            p_res, t_res = py[key], ts.get(key)
            if t_res is None:
                failures.append((key, "missing from the TypeScript run"))
                continue
            if p_res["ok"] != t_res["ok"]:
                failures.append(
                    (key, f"python raised={not p_res['ok']} typescript raised={not t_res['ok']}")
                )
                continue
            if not p_res["ok"]:
                if p_res["code"] != t_res["code"] or p_res["name"] != t_res["name"]:
                    failures.append(
                        (
                            key,
                            f"python {p_res['name']}/{p_res['code']} vs "
                            f"{t_res['name']}/{t_res['code']}",
                        )
                    )
                continue
            if p_res["json"] != t_res["json"]:
                failures.append((key, first_difference(p_res["json"], t_res["json"])))

        # The real claim: TypeScript reproduces the committed snapshot.
        lenient = ts.get(f"{name}::lenient", {})
        if lenient.get("ok"):
            expected = (path.parent / "expected.json").read_bytes().decode("utf-8")
            if lenient["json"] != expected:
                snapshot_failures.append((name, first_difference(expected, lenient["json"])))

    if failures or snapshot_failures:
        if snapshot_failures:
            print(f"parse parity: {len(snapshot_failures)} case(s) diverged from expected.json")
            for name, where in snapshot_failures[:4]:
                print(f"\n  {name}\n    {where}")
        if failures:
            print(f"parse parity: {len(failures)} case/mode combination(s) diverged")
            for key, where in failures[:5]:
                print(f"\n  {key}\n    {where}")
            if len(failures) > 5:
                print(f"\n  ... and {len(failures) - 5} more")
        raise SystemExit(1)

    print(
        f"parse parity: ok -- ALL {len(cases)} cases byte-identical to their committed "
        f"expected.json; {len(cases) * len(MODES)} case/mode combinations agree"
    )


if __name__ == "__main__":
    main()
