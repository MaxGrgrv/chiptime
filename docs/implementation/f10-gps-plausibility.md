# Implementation: F10 — GPS Plausibility

> Feature Spec: [../features/f10-gps-plausibility.md](../features/f10-gps-plausibility.md)

## Summary
`semantics/plausibility.py`: bounce-spike detector (impossible in AND out, plausible when skipped — tunnels survive by construction), Null Island nulling, sport-ceiling table, virtual-GPS exemption with provenance. First lenient/forensic divergence: identical detection, `dropped` vs `ignored` action, values kept in forensic — the ADR-0003 §3 promise made real and test-locked.

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| python/src/chiptime/semantics/plausibility.py | Added | Gate + haversine + ceilings |
| python/src/chiptime/semantics/build.py | Modified | forensic flag, manufacturer lookup, gate hook |
| python/src/chiptime/_api.py | Modified | mode → forensic flag into builder |
| python/src/chiptime/errors.py | Modified | GPS_SPIKES_DROPPED / NULL_ISLAND_DROPPED / VIRTUAL_GPS_EXEMPT |
| corpus/tools/build_fit.py | Modified | gps_spikes / null_island / virtual_gps / treadmill_jump seeds |
| python/tests/test_plausibility.py | Added | 5 tests |

## Corpus Cases Added
gps/{spike-bounce (#53/#54), null-island (#51), virtual-gps-zwift (#57/#83), treadmill-final-jump (#78)}.

## Key Implementation Decisions
1. Bounce-only dropping: requires v_in > ceiling AND v_out > ceiling AND v_skip ≤ ceiling — a sustained jump fails the third condition and is preserved (tunnel/underpass #54).
2. Computed speeds reach canonical output only rounded to 0.1 m/s — libm trig ulp variance can never desynchronize cross-platform snapshots.
3. Exemption is itself provenance (`VIRTUAL_GPS_EXEMPT`) — an agent reading output knows gating was consciously skipped, not forgotten.

## Deviations from Spec
- None.

## Post-Implementation Checklist
- [x] Spec DONE · INDEX/OVERVIEW updated · 138 tests green (55 conformance) · ruff/mypy clean
- [x] Drops counted + provenance'd; forensic never drops
- [x] Skills assessed — no updates needed
