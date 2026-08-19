# Implementation: F8 — Timers, Gaps, Timestamp Policies

> Feature Spec: [../features/f08-timers-gaps-timestamps.md](../features/f08-timers-gaps-timestamps.md)

## Summary
ADR-0005 implemented: stable carry-forward record sort with reorder provenance (#41/#42, lossless layer untouched); defensive timer machine with unbalanced-event tolerance and synthesized final stop (#45); three derived durations (#46, moving honestly None without speed); full gap zoo classification with evidence strings (#43/#44), including corruption gaps keyed to F5's skipped byte ranges; local_timestamp validation exposing `utc_offset_s` (#37 Zwift class); pre-2010 and after-creation sanity flags (#39/#40-approx).

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| python/src/chiptime/semantics/timers.py | Added | TimerState, interval building, moving-time policy |
| python/src/chiptime/semantics/gaps.py | Added | classify_gaps per ADR-0005 §7 |
| python/src/chiptime/semantics/build.py | Modified | Sort → flags → offset validation → per-session timer/moving/gaps |
| python/src/chiptime/model.py | Modified | Activity.utc_offset_s |
| python/src/chiptime/result.py | Modified | utc_offset_s serialization |
| python/src/chiptime/_api.py | Modified | Skipped byte ranges piped into the builder |
| python/src/chiptime/errors.py | Modified | 6 new warning/provenance codes |
| corpus/tools/build_fit.py | Modified | 5 temporal seeds |
| python/tests/test_temporal.py | Added | 6 tests incl. lossless-layer-order proof |

## Corpus Cases Added
5 in `temporal/`: gap-classification (#43-46), missing-final-stop (#45), non-monotonic-records (#41/42), zwift-local-timestamp-1989 (#37/83), pre-2010-timestamps (#39). All 42 prior snapshots regenerated (gaps/utc_offset_s/timer fields joined the schema).

## Key Implementation Decisions
1. Sorting applies ONLY to the semantic timeline — `iter_messages` and canonical `messages` keep true file order; test proves both simultaneously.
2. `corruption` gap kind triangulates F5's `SkippedBytes` ranges against record byte offsets — recovery and semantics compose without new state.
3. No-timer-events files get the record span as timer estimate (minimal-encoder class, taxonomy #88) — reported as-is, not synthesized events.
4. Moving-time dt capped at 30 s so a gap boundary record can't claim an hour of "moving".

## Deviations from Spec
- None.

## Lessons Learned
The gap-classification seed doubles as the timer-machine test — one deliberately rich fixture beats five thin ones for cross-checking interacting policies.

## Post-Implementation Checklist
- [x] Spec DONE · INDEX/OVERVIEW updated · 123 tests green (47 conformance) · ruff/mypy clean
- [x] Reorder/synthesis → provenance; flags → stable warning codes; zero wall-clock
- [x] Skills assessed — no updates needed
