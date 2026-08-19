# Implementation: F20 — Performance Pass

> Feature Spec: [../features/f20-performance-pass.md](../features/f20-performance-pass.md)

## Summary
1.72× with bit-identical output. Landed: decode plans keyed by definition identity (precompiled Struct, signed-adjusted sentinel inline, fast scalar-int path), byte-wise CRC-256 (identity `step(crc,b) == (crc>>8) ^ T[(crc^b)&0xFF]` property-verified), civil-from-days ISO (equality-tested), haversine prefilter (overestimate-only ⇒ safe skips), sortedness early-exit scan, frame-loop payload-size cache.

## Files Changed
| File | Change | Description |
|---|---|---|
| python/src/chiptime/decode.py | Modified | `_FieldPlan` + `_build_plan` + fast/slow split; fast ISO |
| python/src/chiptime/frames.py | Modified | CRC-256; local_sizes cache |
| python/src/chiptime/semantics/{build,plausibility,reconcile}.py | Modified | early-exit sort, prefilter, minor |
| scripts/bench.py | Added | Benchmark harness |
| python/tests/test_hardening.py | Modified | CRC-identity + ISO-equivalence property tests |

## Numbers (Apple Silicon, CPython 3.13)
| Workload | Before | After |
|---|---|---|
| Synthetic 1.04 MB / 40k records | 1033 ms | **599 ms** (1.74 MB/s) |
| Real IRONMAN 1.26 MB / 73k msgs | 1222 ms | **796 ms** |
| Real ROAM ride 332 KB | 346 ms | **211 ms** |

## Lessons Learned
Two rewrite regressions were caught instantly by existing gates (Infinity bypassing diagnostics → unit test; defect-detail drift → corpus snapshot). The corpus-as-proof-harness pattern makes performance work safe.

## Post-Implementation Checklist
- [x] 212 tests green · corpus byte-identical (incl. private tier) · soak clean · ruff/mypy clean
- [x] BACKLOG: bulk columnar decode path (the next multiple), with analysis
