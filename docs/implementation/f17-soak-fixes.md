# Implementation: F17 — Soak-Sprint Fixes

> Feature Spec: [../features/f17-soak-fixes.md](../features/f17-soak-fixes.md)

## Summary
First real-world sprint: 66 files from the maintainer's archive (Wahoo ROAM rides, pool/OW swims, a 5-session IRONMAN race file with 38k records, courses, workouts, platform downloads, fitfiletools outputs) — **zero contract violations**: no crashes in lenient/forensic, byte-identical double parses, every repair strict-clean. Three defects found and fixed, all re-verified against the same archive.

## Findings → Fixes
| Finding (real file) | Fix |
|---|---|
| `fitfiletools-4.fit`: 16-byte valid-but-empty shell → `ok=false` with EMPTY errors | `FIT_NO_CONTENT` error (contract #5); strict stays no-raise (spec-legal); corpus case structural/empty-shell (#16) |
| 4 files repaired to GC-invalid output (`VAL_GC_LOCAL_TIMESTAMP`) | Repair drops impossible local_timestamp on re-emit (+`REPAIR_LOCAL_TIMESTAMP_DROPPED` provenance); latent bug fixed: sentinel 0xFFFFFFFF local raws no longer flag as "implausible" |
| 10 of 20 `DISTANCE_FROZEN` warnings were swim false-positives | Frozen check skipped for `swimming` sessions (#56/#73); decreases/reset stay universal |

## Files Changed
| File | Change | Description |
|---|---|---|
| python/src/chiptime/_api.py, errors.py | Modified | FIT_NO_CONTENT + REPAIR_LOCAL_TIMESTAMP_DROPPED codes |
| python/src/chiptime/repair.py | Modified | `_drop_bad_local_timestamp` on re-emit |
| python/src/chiptime/semantics/{build,reconcile}.py | Modified | Sentinel-raw guard; swim gating |
| scripts/soak_real_files.py | Added | Standing real-file soak harness (privacy-safe output) |
| corpus: structural/empty-shell + seed | Added | #16 in the wild, synthesized twin |

## Soak re-run (verification)
0 contract violations · rejected files now all explained · repaired-but-GC-invalid 4→0 · DISTANCE_FROZEN 20→10 (remaining are cycling files — genuine investigation candidates for F18/F19). Perf datapoint recorded: ~1.0 s/MB pure Python (F20 target).

## Post-Implementation Checklist
- [x] Spec DONE · INDEX updated · 201 tests green (64 conformance) · ruff/mypy clean
- [x] Real-file findings preserved in scratchpad only (privacy); SDK sample files identified in Downloads and BARRED from corpus (license rule)
