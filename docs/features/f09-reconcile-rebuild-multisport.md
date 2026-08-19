# Feature: F9 — Reconciliation, Rebuild, Multisport

> Status: DONE

## Purpose
Never trust a summary (#92): always compute independently, expose disagreement. Rebuild the missing session — the single most demanded repair (#95, research gap #3). First-class multisport (#75). Summary sanity flags (#93/#96/#97).

## Taxonomy Coverage

| Taxonomy item # | Summary | Corpus case(s) |
|---|---|---|
| 92 | Declared vs derived + discrepancy block | reconcile/summary-mismatch |
| 93 | avg > max, negative totals | reconcile/summary-mismatch |
| 95 | Session rebuilt from records | reconcile/no-session-rebuild |
| 96 | Missing activity message flagged | reconcile/no-session-rebuild |
| 97 | Zero-duration session with records; movement w/o distance | reconcile/zero-duration-session |
| 75 | Multisport sessions + transitions correctly bounded | multisport/triathlon |
| 58 (slice) | Derived ascent/descent (3 m hysteresis) | reconcile/summary-mismatch |

## Requirements
1. `semantics/reconcile.py`: per-session declared-vs-derived comparison over elapsed/timer/distance/ascent/descent and avg/max (hr, power, speed, cadence) with per-field tolerance floors + 2–5% relative bands; disagreements land in `session.discrepancies` (never auto-corrected — trust policy is the caller's).
2. Sanity flags: declared avg > declared max → `SUMMARY_AVG_EXCEEDS_MAX`; negative totals → `SUMMARY_NEGATIVE_TOTAL`; declared elapsed 0 with records → `ZERO_DURATION_SESSION`; moving speed with ~zero derived distance → `MOVEMENT_WITHOUT_DISTANCE`.
3. Rebuild (#95): no session messages + records present → `rebuilt: true` session (declared null, bounds from records, sport from the sport message when present) + `SESSION_REBUILT` provenance. No session AND no records → empty sessions list (honest — nothing to model). Missing activity message → `ACTIVITY_MESSAGE_MISSING` warning (M2 repair synthesizes).
4. Multisport: sessions ordered by start_time; transition sessions first-class; `activity.num_sessions` vs actual mismatch → `NUM_SESSIONS_MISMATCH` warning.
5. Derived ascent/descent: 3 m hysteresis over the altitude stream.

## Acceptance Criteria
- [x] no-session file: usable session, rebuilt=true, totals derived, provenance present
- [x] mismatch case: discrepancy entries carry declared/derived/delta; clean seeds stay discrepancy-free
- [x] triathlon: 3 sessions incl. transition, records bounded per session, laps attached to owners

## Public API Impact
`session.discrepancies` populated; new warning/provenance codes; sessions list may be empty.

## Critique & Assessment
- **Alternatives considered:** auto-preferring derived totals (rejected — taxonomy #92 wants both + configurable trust, and "never auto-rewrite" is contract-adjacent); interpolating ascent from GPS altitude when baro absent (rejected — fabrication).
- **Risks identified:** tolerance bands are opinion — encoded as one table, documented, snapshot-locked; hysteresis threshold 3 m is the GoldenCheetah-ish convention.
- **Contract check:** nothing auto-corrected; rebuild marked + provenance'd; empty ≠ fabricated (#8/#16 honesty).
- **Final decision:** APPROVE

## Dependencies
- **Depends on:** F7, F8 · **Depended on by:** F13 (repair emits rebuilt summaries), F14

## Related
- Implementation: [../implementation/f09-reconcile-rebuild-multisport.md](../implementation/f09-reconcile-rebuild-multisport.md)
