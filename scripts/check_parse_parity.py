#!/usr/bin/env python3
"""parse() parity across every corpus case (F35).

Run from repo root:  uv run --project python python scripts/check_parse_parity.py

Two tiers, because the semantic model does not exist in TypeScript until F36
(F35 critique, amendment D1):

  TIER 1  the 11 cases whose output has no `activity` block -- non-activity file
          types, rejects and empties. Compared against the COMMITTED expected.json,
          byte for byte, provenance and warnings included, because at these cases
          every entry originates in intake or decode. This is TypeScript producing
          the corpus snapshot.

  TIER 2  the 61 activity cases, compared on a whitelist of the top-level keys F35
          owns. NOT "everything except activity": 52 of the 61 carry provenance or
          warnings from the semantic layer (SESSION_REBUILT x28,
          ACTIVITY_MESSAGE_MISSING x9, ...), so eliding one key would fail them for
          reasons outside this feature.

          `parts[].messages` is also excluded from tier 2: Python drops record
          messages from the message list when an activity model is present (they
          live in streams instead), and TypeScript has no model yet, so the lists
          legitimately differ until F36.

All three modes are compared, not just lenient.

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

# What F35 owns, for cases whose remaining content is F36's.
TIER2_TOP_KEYS = ("chiptime_schema", "ok", "mode", "source", "recovery", "errors")
TIER2_PART_KEYS = ("file_type", "file_id")

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


def tier2_view(tree: dict) -> dict:
    view = {k: tree[k] for k in TIER2_TOP_KEYS if k in tree}
    view["parts"] = [{k: p.get(k) for k in TIER2_PART_KEYS} for p in tree.get("parts", [])]
    return view


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

    tier1: list[str] = []
    failures: list[tuple[str, str]] = []
    snapshot_failures: list[tuple[str, str]] = []

    for name, path in cases:
        lenient = py[f"{name}::lenient"]
        has_activity = lenient["ok"] and any(
            p.get("activity") is not None for p in json.loads(lenient["json"]).get("parts", [])
        )
        if not has_activity:
            tier1.append(name)

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
            if has_activity:
                a = dumps(tier2_view(json.loads(p_res["json"]))).decode("utf-8")
                b = dumps(tier2_view(json.loads(t_res["json"]))).decode("utf-8")
            else:
                a, b = p_res["json"], t_res["json"]
            if a != b:
                failures.append((key, first_difference(a, b)))

        # Tier 1 also checks the committed snapshot, which is the real claim.
        if not has_activity and lenient["ok"]:
            expected = (path.parent / "expected.json").read_bytes().decode("utf-8")
            actual = ts.get(f"{name}::lenient", {}).get("json")
            if actual is not None and actual != expected:
                snapshot_failures.append((name, first_difference(expected, actual)))

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
        f"parse parity: ok -- {len(tier1)} case(s) byte-identical to their committed "
        f"expected.json; {len(cases) - len(tier1)} activity case(s) matched on the keys "
        f"F35 owns; {len(cases) * len(MODES)} case/mode combinations total"
    )


if __name__ == "__main__":
    main()
