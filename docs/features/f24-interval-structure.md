# Feature: F24 — Interval & Structure Detection (M2.7)

> Status: DONE

## Purpose
Read workout structure the way athletes think in it ("6 × 0:30 @ 385 W", "10 × 100m @ 1:45 rest 0:20") — honestly. Structure is a *reading* of the data, so every result carries its evidence basis, and "no clear structure" is a first-class answer (ADR-0008 §5/§6).

## Requirements
1. `metrics.intervals.detect_structure(session, messages=None, settings=None)` → `IntervalStructure` with `basis` ∈ {steps:workout, laps:manual, lengths:sets, detected:power-steps, detected:speed-steps, none}.
2. **Evidence ladder** (research §10 + §12 survey): structured-workout laps (`wkt_step_index` + `workout_step.intensity`) → manual laps (`lap_trigger=manual`, ≥ 2; single lap ignored per intervals.icu precedent; auto-laps are splits, not structure) → swim sets (active-length grouping with wall-rest threshold, distance = lengths × pool_length from the session message) → deterministic band detection on the primary signal → none.
3. **Detection** (§10): 11-sample rolling median → hysteresis state machine vs session working-median (work ≥ 110%, recovery ≤ 85%) → min-duration merges (20 s work / 15 s recovery) → require ≥ 3 work reps with duration CV < 40%, else `none`. All constants module-level (TS port copies them).
4. **Repeat grouping**: consecutive similar work intervals (swim: equal distance + pace ±10%; other: duration ±25% + intensity ±10%) → `RepeatGroup` with count, means, rest, and a human label via F23 pacing.
5. Per-interval aggregates from streams (record-domain means; lap `declared.avg` fallback when streams absent), null-honest.

## Acceptance Criteria
- [x] ERG-style square-wave power → detected:power-steps, exact rep count + grouping
- [x] Irregular efforts → basis `none` (no fabricated structure)
- [x] Manual-lap and workout-step files route to their bases with kinds mapped from `workout_step.intensity`
- [x] Pool lengths → sets with rest and "N × D" labels; determinism (equal results on re-run)

## Critique & Assessment
- **Alternatives considered:** change-point detection (rejected: stochastic/implementation-defined; hysteresis bands are reproducible everywhere); extending the semantic `Lap` model with trigger/step fields (rejected for M2.7: would alter canonical parse output and force a corpus-wide regen — analytics reads raw messages instead, parse snapshots stay stable per ADR-0008; revisit if a second consumer needs triggers).
- **Contract check:** deterministic, basis on every result, absent data → absent structure, never invented.
- **Final decision:** APPROVE

## Related
- ADR: [0008](../architecture/adrs/0008-analytics-layer.md) · Research: [../research/sport-metrics-domain.md](../research/sport-metrics-domain.md) §10/§12
- Depends on: F23 (profiles, primary signal, pacing) · Depended on by: F25 (report embeds structure)
- Implementation: [../implementation/f24-interval-structure.md](../implementation/f24-interval-structure.md)
