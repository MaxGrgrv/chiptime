# Feature: F25 — Insights, Load, `chiptime analyze` (M2.7)

> Status: DONE

## Purpose
Turn honest streams + structure into a per-workout report an agent (or athlete) can act on: stable insight codes with numeric evidence, load estimators that name their basis, and a CLI verb. Nothing estimated from thin air — absent inputs become `omissions[]`, not numbers.

## Requirements
1. `metrics.load`: `weighted_avg_power` (30-sample 4th-power weighting; zeros real, nulls skipped), `work_kj` (dt-capped), `intensity_ratio`, `load_score` (h × IR² × 100), Banister `trimp` (sex-labeled coefficient), `workout_load` ladder power+ftp → hr-trimp → None with **≥ 50% HR-coverage guard** (sparse swim HR must not silently understate), `fitness_fatigue_form` EWMA (42 d / 7 d, form lags a day, seeds at 0 — stated).
2. `metrics.insights`: `WorkoutReport` (pace/speed with basis, primary stats, weighted power, variability, kJ, power curve, SWOLF, splits, structure, zone time via the F23 ladder, load, omissions) + `Insight{code, message, evidence}` with registry `INSIGHT_CODES` (PACING_NEGATIVE/POSITIVE_SPLIT ±2%, HR_DRIFT_HIGH >5% EF fall, COASTING_HIGH >25% zero-W on rides, WORKOUT_STRUCTURE); `analyze(result, settings)` per session.
3. CLI: `chiptime analyze FILE [--json|-o] [--ftp --max-hr --resting-hr --sex --hr-zones --power-zones]`; parse-derived exit codes; deterministic sorted-key JSON; honest line when a file has no sessions.
4. Insight codes published in docs/for-agents.md (generator extended).

## Acceptance Criteria
- [x] TRIMP matches the published formula on a synthetic hour (±0.5); female coefficient lower
- [x] 1 h at FTP → load ≈ 100 by definition; ladder bases exact; no-threshold → omission
- [x] Real-file soak: Zwift structured ride reads "3 x 10:00 @ 194 W rest 3:24"; pool sets group; sparse-HR swims omit load with the coverage reason; empty/damaged files state it
- [x] Deterministic JSON report; all 273 tests green

## Critique & Assessment
- **Alternatives considered:** exposing load without settings via estimated FTP (rejected hard — ADR-0008 §4); putting the report into canonical parse output (rejected — parse snapshots stay stable, analytics evolve on their own clock); TRIMP without coverage guard (rejected after real-file soak showed 2–17% HR coverage on swims producing load 3 where ~117 was plausible — the guard converts a silent lie into a stated omission).
- **Contract check:** every number carries basis or lands in omissions; deterministic; trademark-safe naming verified (research §12).
- **Final decision:** APPROVE

## Related
- ADR: [0008](../architecture/adrs/0008-analytics-layer.md) · Depends on: F23, F24 · Depended on by: —
- Implementation: [../implementation/f25-insights-load-analyze.md](../implementation/f25-insights-load-analyze.md)
