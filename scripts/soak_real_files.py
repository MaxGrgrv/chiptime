#!/usr/bin/env python3
"""Soak-test chiptime against a directory of real-world FIT files.

Usage:  uv run --project python python scripts/soak_real_files.py <dir> [out.json]

Per file, checks the behavior contract:
  - lenient and forensic parse must NEVER raise
  - double-parse must be byte-identical (determinism)
  - strict may raise, but only typed FitErrors
  - activities must survive repair -> strict re-parse
Prints an aggregate report; NEVER prints coordinates, serials, or field values
(privacy: real files stay summarized). Writes machine-readable results JSON.
"""

from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python" / "src"))

import chiptime
from chiptime.repair import NotRepairableError, repair
from chiptime.validate import validate


def soak_one(path: Path) -> dict:
    r: dict = {"file": path.name, "size": path.stat().st_size}
    data = path.read_bytes()
    t0 = time.perf_counter()
    try:
        res = chiptime.parse(data)
    except Exception:
        r["CONTRACT_VIOLATION"] = "lenient raised"
        r["traceback"] = traceback.format_exc(limit=4)
        return r
    r["parse_ms"] = round((time.perf_counter() - t0) * 1000, 1)
    n_msgs = sum(len(p.messages) for p in res.parts)
    n_unknown = sum(1 for p in res.parts for m in p.messages if m.name.startswith("unknown_"))
    a = res.activity
    r.update(
        {
            "ok": res.ok,
            "file_type": res.file_type,
            "parts": len(res.parts),
            "messages": n_msgs,
            "unknown_pct": round(100 * n_unknown / n_msgs, 1) if n_msgs else 0.0,
            "records": sum(s.records.n for s in a.sessions) if a else 0,
            "sessions": len(a.sessions) if a else 0,
            "gaps": [g.kind for g in a.gaps] if a else [],
            "errors": [e.code for e in res.errors],
            "warnings": sorted({w.code for w in res.warnings}),
            "provenance": sorted({p.code for p in res.provenance}),
        }
    )
    if res.recovery:
        r["recovery"] = {
            "recovered": res.recovery.recovered_records,
            "bytes_skipped": res.recovery.bytes_skipped,
            "resyncs": res.recovery.resync_count,
        }

    try:
        if chiptime.parse(data).to_canonical_json() != res.to_canonical_json():
            r["CONTRACT_VIOLATION"] = "nondeterministic"
    except Exception:
        r["CONTRACT_VIOLATION"] = "canonical serialization raised"
        r["traceback"] = traceback.format_exc(limit=4)

    try:
        chiptime.parse(data, mode="forensic")
    except Exception:
        r["CONTRACT_VIOLATION"] = "forensic raised"
        r["traceback"] = traceback.format_exc(limit=4)

    try:
        chiptime.parse(data, mode="strict")
        r["strict"] = "ok"
    except chiptime.FitError as e:
        r["strict"] = f"raise:{e.code}"
    except Exception:
        r["CONTRACT_VIOLATION"] = "strict raised a non-FitError"
        r["traceback"] = traceback.format_exc(limit=4)

    if res.ok and res.file_type == "activity":
        try:
            rr = repair(data)
            r["repair"] = "strict-ok" if rr.output_strict_ok else "NOT-STRICT"
            gc = validate(rr.data, "garmin-connect")
            r["repair_gc_errors"] = sorted({f.code for f in gc if f.level == "error"})
        except NotRepairableError as e:
            r["repair"] = f"refused:{e.code}"
        except Exception:
            r["CONTRACT_VIOLATION"] = "repair raised unexpectedly"
            r["traceback"] = traceback.format_exc(limit=4)
    return r


def main() -> int:
    root = Path(sys.argv[1]).expanduser()
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    files = sorted(root.glob("**/*.fit")) + sorted(root.glob("**/*.FIT"))
    files = [f for f in files if f.is_file()][:500]
    results = [soak_one(f) for f in files]

    violations = [r for r in results if "CONTRACT_VIOLATION" in r]
    not_ok = [r for r in results if not r.get("ok") and "CONTRACT_VIOLATION" not in r]
    repaired_bad = [
        r
        for r in results
        if r.get("repair") not in (None, "strict-ok")
        and not str(r.get("repair", "")).startswith("refused")
    ]
    gc_fail = [r for r in results if r.get("repair_gc_errors")]
    slow = sorted(results, key=lambda r: -r.get("parse_ms", 0))[:5]

    print(f"\n=== SOAK: {len(results)} files ===")
    print(f"contract violations: {len(violations)}")
    for r in violations:
        print(f"  !! {r['file']}: {r['CONTRACT_VIOLATION']}")
        print("     " + r.get("traceback", "").strip().replace("\n", "\n     ")[-600:])
    print(f"not ok (rejected): {len(not_ok)}")
    for r in not_ok:
        print(f"  - {r['file']}: errors={r['errors']}")
    print(f"repair not strict-clean: {len(repaired_bad)}")
    for r in repaired_bad:
        print(f"  - {r['file']}: {r['repair']}")
    print(f"repaired-but-GC-invalid: {len(gc_fail)}")
    for r in gc_fail:
        print(f"  - {r['file']}: {r['repair_gc_errors']}")

    types: dict[str, int] = {}
    for r in results:
        types[r.get("file_type", "?")] = types.get(r.get("file_type", "?"), 0) + 1
    print(f"file types: {types}")
    high_unknown = [r for r in results if r.get("unknown_pct", 0) > 30]
    print(f"files with >30% unknown messages: {len(high_unknown)}")
    all_warn: dict[str, int] = {}
    for r in results:
        for w in r.get("warnings", []):
            all_warn[w] = all_warn.get(w, 0) + 1
    print("warning frequency:", dict(sorted(all_warn.items(), key=lambda kv: -kv[1])))
    strict_fail = [r for r in results if str(r.get("strict", "")).startswith("raise")]
    print(f"strict-mode rejections: {len(strict_fail)}")
    print(
        "slowest:", [(r["file"], f"{r.get('parse_ms')}ms", f"{r['size'] // 1024}KB") for r in slow]
    )

    if out_path:
        out_path.write_text(json.dumps(results, indent=1))
        print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
