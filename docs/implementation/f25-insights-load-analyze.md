# Implementation: F25 — Insights, Load, `chiptime analyze`

> Spec: [features/f25-insights-load-analyze.md](../features/f25-insights-load-analyze.md) · ADR: [0008](../architecture/adrs/0008-analytics-layer.md) · 2026-08-18

## What was built
- `metrics/load.py` — published-formula estimators (docstring-cited): weighted
  average power (rolling-mean cumulative implementation, O(n)), work kJ,
  intensity ratio, load_score, Banister TRIMP (k=1.92/1.67, unset sex uses the
  male coefficient and the basis string says so), `hr_coverage_fraction` +
  `TRIMP_MIN_COVERAGE = 0.5` guard, `workout_load` estimator ladder,
  `fitness_fatigue_form` day-grid EWMA (missing days = 0 load; form(t) =
  fitness(t-1) − fatigue(t-1); explicit 0 seed).
- `metrics/insights.py` — `analyze_session`/`analyze`, `WorkoutReport.to_dict()`
  via a recursive dataclass→plain converter; half-split pacing comparison
  (min 60 paired samples), EF drift, coasting share, structure insight from
  F24 repeats. `INSIGHT_CODES` registry feeds the generated agent docs.
- `cli.py` — `analyze` verb; `_parse_bounds` validates ascending zone bounds
  (exit 64); text report prints basis strings, omissions, and an honest
  "no activity sessions" line; JSON is sorted-key/compact (deterministic).
- `scripts/gen_agent_docs.py` — new "Insight codes" section (script-only
  import of the optional layer).

## Real-file soak findings (drove two fixes)
1. Swim HR coverage 2–17% made TRIMP math-true but load-false (3 vs ~117
   plausible) → coverage guard + explicit omission message.
2. `resync-damaged` (non-activity content) printed nothing → explicit
   empty-report line. The 814-byte just-started Zwift file correctly reports
   its one-second session — honest, not a bug.

## Verification
14 tests (`tests/test_insights_load.py`): formula anchors, ladder bases,
EWMA lag semantics, insight thresholds both sides, JSON-readiness, CLI
end-to-end on corpus cases (json + text + usage-error), coverage guard.
Full gate green; 273 tests total.

## Deviations from spec
- None.
