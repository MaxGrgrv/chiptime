# Implementation: F23 — Sport Profiles + Pacing Foundation

> Spec: [features/f23-sport-profiles-pacing.md](../features/f23-sport-profiles-pacing.md) · ADR: [0008](../architecture/adrs/0008-analytics-layer.md) · 2026-08-18

## What was built

`chiptime.metrics` converted from module to package (F21 basics moved to
`metrics/_basics.py`, all names re-exported — `from chiptime import
metrics; metrics.mean_max(...)` unchanged). New modules:

| Module | Contents |
|---|---|
| `metrics/settings.py` | `AthleteSettings` — the only door for thresholds (ftp_w, css, max/resting HR, lthr, explicit zone bounds, sex for TRIMP). All optional. |
| `metrics/sports.py` | `SportProfile` (frozen dataclass) + registry; `profile_for(session)` maps (sport, sub_sport) → profile incl. pool-vs-open-water and indoor-rowing routing; `primary_signal()` resolves power-vs-speed against streams actually present; `cadence_display()` with the labeled per-leg ×2 run heuristic (`RUN_PER_LEG_CADENCE_MAX = 130`). |
| `metrics/pacing.py` | `pace_seconds` / `speed_from_pace` / `format_pace` (half-up rounding, tenths for /500m) / `format_speed_kmh`; Concept2 `split_500m_to_watts` ↔ `watts_to_split_500m` (W = 2.80/pace³); `distance_splits()` — boundary-interpolated distance splits with per-split HR/power means + ascent/descent, partial-split flag; `session_pace_s()` with moving→timer→elapsed denominator ladder and basis string. |
| `metrics/zones.py` | `hr_zone_bounds` / `power_zone_bounds` — settings > in-file `hr_zone`/`power_zone` messages > (None, None); returns basis. |

## Contract notes
- Pace is never averaged (inverse trap): splits and session pace aggregate
  distance/time, convert last. Standstill pace = None, not ∞.
- Null-honest: absent streams → None fields, `[]` for no distance stream.
- Deterministic: explicit half-up rounding (no banker's), no wall-clock.
- Core still never imports metrics (existing enforcement test covers the
  package unchanged).

## Verification
- 11 new tests in `python/tests/test_sport_pacing.py` (profiles, signal
  resolution, cadence doubling, pace exactness incl. "4:20"/"1:52.5",
  Concept2 round-trip < 0.1 W + published 2:00 → 202.5 W anchor,
  interpolated splits + ascent, absent-stream honesty, denominator ladder,
  zone ladder). Full gate green (ruff, format, mypy --strict, corpus, 249
  tests).

## Deviations from spec
- Private-tier real-file splits assertion covered by the existing private
  corpus determinism run rather than a dedicated test; a real-file splits
  smoke lands with F25's `chiptime analyze` (which exercises the whole
  chain on the ROAM/IRONMAN files).
