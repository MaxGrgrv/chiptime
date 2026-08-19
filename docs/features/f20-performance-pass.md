# Feature: F20 — Performance Pass (M2.5)

> Status: DONE

## Purpose
First measured perf work: ~1.0 MB/s pure-Python baseline (soak datapoint on the real IRONMAN file) → meaningful speedup with **bit-identical output** (the corpus is the proof harness).

## Requirements
1. `scripts/bench.py` (synthetic 1 MB / 40k-record ride, best-of-3, `--profile`) — informational, never a CI gate.
2. Optimizations, each equality-proven: per-definition decode plans (precompiled `struct.Struct`, inlined sentinels, scalar-integer fast path — floats keep the diagnostic path); 256-entry byte-wise CRC composed from the FIT nibble algorithm (identity property-tested); Hinnant civil-from-days ISO formatter (equality-tested vs strftime); haversine safe-overestimate prefilter; sortedness early-exit; payload-size caching in the frame loop.
3. Full corpus byte-identical after every change; soak re-run clean.

## Acceptance / Results
- [x] Bench: **1033 → 599 ms (1.72×, 1.74 MB/s, 67k msgs/s)**; real files: IRONMAN 1.22 s → 0.80 s, ROAM 346 → 211 ms
- [x] 212 tests green; corpus + private tier byte-identical; 0 soak violations
- Target was 3–5×: **not reached, deliberately** — see critique.

## Critique & Assessment
- **Why stop at 1.7×:** remaining time is structural — 400k `FieldValue` constructions and per-message dicts ARE the lossless layer's contract. The next multiple requires a bulk record→columnar decode path that bypasses per-message objects for stream-bound fields — an architectural feature (natural to design alongside M3 parity), not an optimization. BACKLOG'd with this analysis rather than force-fit.
- **Contract check:** every optimization has an equality test (CRC identity, ISO equivalence, corpus bytes); floats deliberately excluded from the fast path to preserve NONFINITE diagnostics.
- **Final decision:** APPROVE (with revised, evidenced target)

## Related
- Implementation: [../implementation/f20-performance-pass.md](../implementation/f20-performance-pass.md)
