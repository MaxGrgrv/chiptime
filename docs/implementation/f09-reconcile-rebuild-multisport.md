# Implementation: F9 — Reconciliation, Rebuild, Multisport

> Feature Spec: [../features/f09-reconcile-rebuild-multisport.md](../features/f09-reconcile-rebuild-multisport.md)

## Summary
`semantics/reconcile.py`: tolerance-banded declared-vs-derived comparison filling `session.discrepancies` (never auto-correcting), sanity flags (#93/#97), 3 m-hysteresis ascent/descent. `build.py`: session rebuild from records with sport-message lookup (#95) + `SESSION_REBUILT` provenance, honest empty-session list when nothing exists, `ACTIVITY_MESSAGE_MISSING` (#96) and `NUM_SESSIONS_MISMATCH` flags, sessions sorted by start. Multisport verified end-to-end: swim/transition/bike each own exactly their records and laps.

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| python/src/chiptime/semantics/reconcile.py | Added | Tolerances, comparison, sanity flags, ascent/descent |
| python/src/chiptime/semantics/build.py | Modified | Rebuild path, empty honesty, session sort, reconcile hook |
| python/src/chiptime/errors.py | Modified | 7 new codes |
| corpus/tools/build_fit.py | Modified | multisport / summary_mismatch / no_session / zero_duration seeds |
| python/tests/test_reconcile.py | Added | 6 tests |

## Corpus Cases Added
multisport/triathlon (#75), reconcile/summary-mismatch (#92/#93/#58-slice), reconcile/no-session-rebuild (#95/#96), reconcile/zero-duration-session (#97). Session-less older seeds now rebuild — snapshots regenerated.

## Key Implementation Decisions
1. Trust policy stays with the caller: discrepancies carry declared+derived+delta; chiptime never picks a winner (taxonomy #92's "configurable trust policy" becomes trivial downstream).
2. Rebuild consults the `sport` message (12) — the Zwift crash file class carries one even without a session.
3. No records + no session ⇒ `sessions: []`, not a fabricated shell — the #16 honesty rule generalized.
4. Tolerance table is deliberately one visible dict per category — the JS port copies numbers, not logic archaeology.

## Deviations from Spec
- None.

## Post-Implementation Checklist
- [x] Spec DONE · INDEX/OVERVIEW updated · 133 tests green (51 conformance) · ruff/mypy clean
- [x] Rebuild/synthesis → provenance; flags → stable codes; nothing auto-corrected
- [x] Skills assessed — no updates needed
