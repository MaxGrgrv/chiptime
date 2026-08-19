# Feature: F21 — HRV Depth + Analytics Foundation (M2.5)

> Status: DONE

## Purpose
Surface HRV as first-class model data (#72 — "often silently dropped by parsers"), and lay the analytics foundation the PRD deferred: an optional, zero-dep `chiptime.metrics` module + pandas bridge — analytics that can't be silently corrupted because they sit on streams where sentinels are already null and 0 ≠ null (#64's payoff).

## Taxonomy Coverage
| # | Summary | Case |
|---|---|---|
| 72 | HRV/RR arrays surfaced, not dropped | protocol/array-fields (retagged +72; model now carries hrv_intervals_s) |
| 73 (depth) | SWOLF on real lengths | metrics tests vs the real pool swim (private tier) |

## Requirements
1. `Activity.hrv_intervals_s: list[float]` — RR intervals concatenated in file order (sentinel tails already trimmed by decode); canonical JSON field.
2. `chiptime/metrics.py` (pure stdlib, imported only on demand, NEVER by core):
   - `mean_max(values, windows)` — rolling best averages (power/pace curves), record-domain (≡ time-domain at 1 Hz, documented), a window counts only when ≥90% of its samples are present (null-honesty).
   - `time_in_zones(times, values, bounds)` — dt-weighted with the ADR-0005 30 s dt cap.
   - `swolf(session)` — per-active-length strokes + seconds, and the average.
   Generic names only — no TrainingPeaks trademarks.
3. `Records.to_pandas()` + `chiptime[pandas]` optional extra (guarded import; core stays zero-dep).
4. Real-file grounding: SWOLF numbers verified against the promoted real pool swim.

## Critique & Assessment
- **Alternatives considered:** time-domain resampling for mean_max v1 (rejected: interpolation smuggles fabricated samples into analytics; record-domain with honest 1 Hz caveat beats quietly invented data); separate chiptime-metrics package (rejected for now: an optional module has zero packaging cost and can split later).
- **Contract check:** metrics never mutate; missing data shrinks coverage rather than being filled; core import graph unchanged (test-enforced: importing chiptime must not import metrics or pandas).
- **Final decision:** APPROVE

## Related
- Implementation: [../implementation/f21-swim-hrv-metrics.md](../implementation/f21-swim-hrv-metrics.md)
