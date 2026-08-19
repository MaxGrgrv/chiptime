#!/usr/bin/env python3
"""Regenerate every corpus case from its case.json build pipeline.

Usage (from repo root):
    python corpus/tools/gen_all.py            # verify inputs match recorded sha256
    python corpus/tools/gen_all.py --update   # (re)write inputs + record sha256
    python corpus/tools/gen_all.py --expected # also regenerate expected.json via chiptime
                                              # (requires: uv run --project python ...)

Build pipeline ops: {"op": "seed", "name": ..., [kwargs]} | {"op": "payload", "kind": ...}
followed by any op from corrupt.py, e.g. {"op": "truncate", "at": 1234}.
The "chain" op accepts {"seeds": ["name", ...]} resolved via build_fit.SEEDS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
CORPUS = TOOLS.parent
sys.path.insert(0, str(TOOLS))

import build_fit
import corrupt


def build_input(pipeline: list[dict]) -> bytes:
    data = b""
    for step in pipeline:
        step = dict(step)
        op = step.pop("op")
        if op == "seed":
            name = step.pop("name")
            data = build_fit.build_seed(name, **step)
        elif op == "payload":
            data = corrupt.payload(step["kind"])
        elif op == "chain":
            extra = [build_fit.build_seed(n) for n in step["seeds"]]
            data = corrupt.chain(data, seeds=extra)
        else:
            fn = getattr(corrupt, op)
            data = fn(data, **step)
    return data


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="write inputs + record sha256")
    ap.add_argument("--expected", action="store_true", help="regenerate expected.json snapshots")
    ap.add_argument("--only", help="limit to cases whose path contains this substring")
    args = ap.parse_args()

    case_files = sorted(CORPUS.glob("cases/*/*/case.json"))
    case_files += sorted(CORPUS.glob("private/cases/*/*/case.json"))
    if args.only:
        case_files = [c for c in case_files if args.only in str(c)]

    failures: list[str] = []
    manifest: list[str] = []
    for cf in case_files:
        case = json.loads(cf.read_text())
        rel = cf.parent.relative_to(CORPUS)
        if "private" not in str(rel):
            manifest.append(str(rel))

        if case["build"] == "external":  # real file (ADR-0007): verify, never rebuild
            input_path = cf.parent / "input.fit"
            if not input_path.exists():
                failures.append(f"{rel}: external input.fit missing")
                continue
            if sha256(input_path.read_bytes()) != case.get("input_sha256"):
                failures.append(f"{rel}: external input.fit does not match recorded sha")
            if args.expected:
                import chiptime

                result = chiptime.parse(input_path.read_bytes(), mode="lenient")
                (cf.parent / "expected.json").write_bytes(result.to_canonical_json())
                print(f"wrote {rel}/expected.json")
            continue

        data = build_input(case["build"])
        data2 = build_input(case["build"])
        if data != data2:
            failures.append(f"{rel}: build pipeline is nondeterministic")
            continue

        input_path = cf.parent / "input.fit"
        digest = sha256(data)
        if args.update:
            input_path.write_bytes(data)
            if case.get("input_sha256") != digest:
                case["input_sha256"] = digest
                cf.write_text(json.dumps(case, indent=2, sort_keys=False) + "\n")
            print(f"wrote {rel}/input.fit ({len(data)} bytes)")
        else:
            if not input_path.exists():
                failures.append(f"{rel}: input.fit missing (run with --update)")
                continue
            if sha256(input_path.read_bytes()) != digest:
                failures.append(f"{rel}: input.fit does not match build pipeline")
                continue
            if case.get("input_sha256") != digest:
                failures.append(f"{rel}: recorded input_sha256 stale")

        if args.expected:
            import chiptime  # deferred: only needed for snapshot regeneration

            result = chiptime.parse(data, mode="lenient")
            (cf.parent / "expected.json").write_bytes(result.to_canonical_json())
            print(f"wrote {rel}/expected.json")

    if not args.only:  # a filtered run must never shrink the manifest
        (CORPUS / "MANIFEST.json").write_text(
            json.dumps({"manifest_schema": 1, "cases": manifest}, indent=2) + "\n"
        )

    if failures:
        print("\nFAILURES:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    print(f"ok: {len(manifest)} cases verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
