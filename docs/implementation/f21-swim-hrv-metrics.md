# Implementation: F21 — HRV Depth + Analytics Foundation

> Feature Spec: [../features/f21-swim-hrv-metrics.md](../features/f21-swim-hrv-metrics.md)

## Summary
`Activity.hrv_intervals_s` (#72, serialized); `chiptime/metrics.py` — `mean_max` (coverage-gated rolling bests), `time_in_zones` (dt-capped), `swolf` (verified on the real 59-length pool swim: plausible values, exact synthetic expectations); `Records.to_pandas()` behind the `chiptime[pandas]` extra. Core import graph unchanged — test-enforced (importing chiptime must not pull metrics or pandas).

## Files Changed
| File | Change | Description |
|---|---|---|
| python/src/chiptime/metrics.py | Added | The analytics module (optional import) |
| python/src/chiptime/{model,result}.py, semantics/build.py | Modified | HRV surfacing + to_pandas |
| python/pyproject.toml | Modified | `[pandas]` extra; version 0.3.0 |
| python/tests/test_metrics.py | Added | 8 tests incl. import-graph guard + real-file SWOLF (private-tier-conditional) |
| corpus/cases/protocol/array-fields | Retagged | +#72; snapshots regenerated (hrv_intervals_s joined the schema) |

## Key Decisions
1. mean_max stays in the record domain with an honest 1 Hz caveat — interpolation would smuggle fabricated samples into analytics (the exact sin the library exists to prevent).
2. Coverage gate (≥90%) makes missing data shrink answers instead of skewing them.
3. Real-file tests skip cleanly when the private tier is absent — public CI meaning preserved.

## Post-Implementation Checklist
- [x] 220 tests green (public) · private snapshots regenerated · ruff/mypy clean
- [x] Zero runtime deps held; pandas strictly optional
