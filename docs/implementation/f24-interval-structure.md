# Implementation: F24 — Interval & Structure Detection

> Spec: [features/f24-interval-structure.md](../features/f24-interval-structure.md) · ADR: [0008](../architecture/adrs/0008-analytics-layer.md) · 2026-08-18

## What was built

`chiptime/metrics/intervals.py` — `detect_structure(session, messages=None,
settings=None)` → frozen `IntervalStructure{basis, intervals, repeats, note}`.

**Evidence ladder** (first rung that yields structure wins):
1. `steps:workout` — laps carrying `wkt_step_index`; kinds mapped from
   `workout_step.intensity` (active/interval→work, rest, recovery, warmup,
   cooldown; unknown→steady).
2. `laps:manual` — ≥ 2 laps with `lap_trigger=manual` (a single lap is
   ignored and auto-laps are splits, per platform survey §12); all laps
   become intervals, kind classified relative to the band reference.
3. `lengths:sets` — pool swims: active lengths joined when wall rest
   < `SWIM_SET_REST_MIN_S` (10 s); distance = lengths × `pool_length` from
   the session message (fallback derived-distance ÷ lengths).
4. `detected:power-steps` / `detected:speed-steps` — 11-sample rolling
   median → hysteresis state machine (work ≥ 110%, recovery ≤ 85% of the
   band reference) → sub-minimum runs merge into their neighbor (20 s work
   / 15 s recovery) → gates: ≥ 3 work reps AND duration CV ≤ 40%.
5. `none` — with a `note` saying why (too little data / too few reps /
   too varied). Honest non-structure is a result, not a failure.

**Band reference** — the design find of the feature: the session median
sits *on* whichever effort level dominates, so a recovery sample at the
median can never test ≤ 85% of it. The reference is instead the midpoint
of the 20th/80th percentiles of positive smoothed samples
(`_band_reference`), which lands between the levels for any work:rest duty
cycle. Used identically for stream detection and lap classification.

**Repeat grouping** — consecutive similar work intervals (swim: equal
length count; else duration ±25% + intensity ±10%) with ≥ 2 reps become
`RepeatGroup`s labeled in athlete notation via F23 pacing: `"6 x 0:30 @
300 W"`, `"4 x 100m @ 1:44/100m rest 0:20"`; mean rest from the recovery
interval following each rep.

Aggregates are stream-based over each interval's time range (record-domain
means), with lap-declared `avg_power`/`avg_speed`/`avg_heart_rate`/
`total_distance` as fallback when streams are absent. All constants are
module-level for the TS port; every path is deterministic (RUF-clean ASCII
`x` in labels).

## Verification
10 tests in `python/tests/test_intervals.py`: ERG square-wave exactness
(6 reps, label, grouped mean, rerun-equality), irregular-effort and
too-few-reps honesty, run speed-steps with pace labels, no-stream honesty,
manual-lap routing + classification + rests, single-lap fallthrough,
auto-lap fallthrough, workout-step kind mapping, swim set grouping with
pool length. Full gate green (ruff+format+mypy+259-test suite).

## Deviations from spec
- Zone-based lap classification (settings-aware) reserved to BACKLOG; the
  relative band reference covers files without thresholds, which is the
  honest default.
