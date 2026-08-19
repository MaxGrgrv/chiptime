# Feature: F23 — Sport Profiles + Pacing Foundation (M2.7)

> Status: DONE

## Purpose
The layer that knows running pace is not cycling speed is not swim /100 is not rowing /500 (research doc §0): a data-driven sport-profile registry, pace math done right (inverse-metric safe), distance splits, and the rowing watts↔split bridge.

## Requirements
1. `metrics/` package (back-compat: existing `mean_max`/`time_in_zones`/`swolf` re-exported).
2. `metrics.sports`: `SportProfile` registry per research §0 — primary signal (power|speed), pace style (per_km|per_100m|per_500m|speed), moving-pace denominator policy, cadence display convention (incl. the run per-leg ×2 heuristic, labeled); `profile_for(session)`.
3. `metrics.pacing`: `pace_seconds(speed_mps, style)`, `format_pace(seconds, style)` ("4:05" / "1:45.3"), `speed_from_pace`, Concept2 `watts_to_split_500m`/`split_500m_to_watts` (published formula, cited); `distance_splits(session, split_m)` → per-split duration/pace/avg-HR/ascent from streams (cumulative-distance based, null-honest).
4. `AthleteSettings` dataclass (ftp_w, threshold_pace_per_km, css_per_100m, max_hr, resting_hr, lthr) — the only door for thresholds (ADR-0008 §4).
5. Zone resolution ladder: explicit settings > in-file zone messages (hr_zone/power_zone) > omitted-with-note.

## Acceptance Criteria
- [x] Splits on the ROAM ride and IRONMAN legs (private-tier tests) sane; synthetic exact
- [x] Pace formatting exact (259.5 s/km → "4:20"; swim "1:45/100m"; row "1:52.5/500m")
- [x] Concept2 round-trip watts↔split within 0.1 W

## Critique & Assessment
- **Alternatives considered:** per-sport subclasses with methods (rejected: profiles-as-data keeps logic in one place and ports to TS as a table); auto-detecting FTP/CSS from the workout (rejected hard: ADR-0008 §4 — fabricated thresholds corrupt every downstream number silently).
- **Contract check:** deterministic; pace never averaged; absent streams → absent splits fields, never zeros.
- **Final decision:** APPROVE

## Related
- ADR: [0008](../architecture/adrs/0008-analytics-layer.md) · Research: [../research/sport-metrics-domain.md](../research/sport-metrics-domain.md)
- Implementation: [../implementation/f23-sport-profiles-pacing.md](../implementation/f23-sport-profiles-pacing.md)
