# ADR-0008: Analytics layer — sport profiles, honest estimators, neutral names

> Status: ACCEPTED · 2026-08-18 · Features: F23–F25 (M2.7)

## Context
Analytics on top of honest streams (docs/research/sport-metrics-domain.md).
Danger zones: fabricating thresholds, averaging paces, trademarked names,
nondeterministic detection.

## Decisions
1. **`chiptime.metrics` becomes a package**, still optional, still zero-dep,
   still never imported by the core (test-enforced). Everything in it is a
   pure function of (parsed model, optional AthleteSettings).
2. **Sport profiles are data**: one registry mapping (sport, sub_sport) →
   primary intensity signal, pace style, denominators, cadence display
   convention. Analytics code branches on profile fields, never on sport
   names scattered through logic.
3. **All internal math in SI (m/s, W, s); pace is presentation** — computed
   from aggregate speed, never averaged directly (inverse-metric trap).
4. **Thresholds come from the user or the file, never from inference**:
   FTP / threshold pace / CSS / HR anchors arrive via `AthleteSettings` or
   in-file messages (`zones_target`, `hr_zone`, `power_zone`, `user_profile`).
   Absent threshold ⇒ that analysis is omitted with a note — a missing number
   beats an invented one (contract #8 extended upward).
5. **Every derived number carries its basis**: insights and load figures are
   typed objects with a `basis` field (`power+ftp`, `hr-trimp`,
   `duration-only`, `laps:manual`, `detected:power-steps`) so downstream
   consumers—human or agent—know what they're standing on.
6. **Detection is deterministic**: rolling medians + named threshold
   constants; "no clear structure" is a first-class result. No RNG, no
   wall-clock, no iteration-order luck (same rules as the parser).
7. **Neutral naming**: `weighted_avg_power`, `intensity_ratio`, `load_score`,
   `fitness`/`fatigue`/`form`, `hr_drift_pct`, `trimp`, `css`, `split_500m`.
   Published formulas cited in docstrings; trademarked labels (NP/TSS/IF/
   CTL/ATL/TSB) never appear in API or output.

## Consequences
- Analytics results are reproducible byte-for-byte and portable to the TS
  twin by copying constants + this ADR.
- Some popular numbers are absent without user input (zones, load_score
  without FTP) — by design, stated in output.
