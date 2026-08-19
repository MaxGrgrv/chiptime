# Feature: F10 — GPS Plausibility (Tier-1 Slice)

> Status: DONE

## Purpose
Value-level truth gates for positions: Null Island interleave (#51), speed-gated bounce-spike rejection (#53), virtual-GPS exemption so Zwift worlds are never "corrected" (#57), and the treadmill final-jump non-flag (#78). First real lenient/forensic divergence: lenient drops with provenance, forensic only annotates (ADR-0003 §3).

## Taxonomy Coverage

| Taxonomy item # | Summary | Corpus case(s) |
|---|---|---|
| 51 | (0,0) and sentinel positions interleaved with valid ones | gps/null-island |
| 53 | Single-record teleport spikes (bounce pattern) | gps/spike-bounce |
| 57 | Virtual GPS (Watopia) must not be filtered | gps/virtual-gps-zwift |
| 78 | Treadmill end-of-run distance jump is legit | gps/treadmill-final-jump |
| 54 (boundary) | Sustained jump (tunnel) is NOT a spike — kept | gps/spike-bounce (tunnel segment) |

## Requirements
1. `semantics/plausibility.py`: position gate over lat/long streams.
2. **Bounce detector** (#53): point i is an outlier only when implied speed into it AND out of it both exceed the sport ceiling while skipping it is plausible — a sustained jump (tunnel re-acquisition, #54) is never dropped.
3. Sport ceilings (m/s): running/walking-class 12.5/8, cycling 42, swimming 4, default 55 — one visible table.
4. Null Island: exact (0.0, 0.0) pairs are absence → nulled (lenient) / annotated (forensic); sentinels already null from decode.
5. Virtual exemption (#57): manufacturer zwift OR sub_sport virtual_activity → gate skipped entirely, provenance notes the exemption.
6. Lenient: offending lat/long values → None + provenance (`GPS_SPIKES_DROPPED`, `NULL_ISLAND_DROPPED`, action dropped, counts + worst implied speed rounded to 0.1). Forensic: identical detection, values kept, action `ignored`.
7. Determinism guard: computed speeds appear in output rounded to 0.1 (libm trig last-ulp variance must never reach canonical bytes).

## Acceptance Criteria
- [x] Bounce dropped in lenient, kept in forensic; tunnel jump untouched in both
- [x] Zwift virtual coordinates byte-identical through the gate
- [x] Null Island pairs nulled with count; valid fixes untouched

## Public API Impact
None structural — provenance/warning codes only.

## Critique & Assessment
- **Alternatives considered:** Kalman/median smoothing (#55) — rejected for M1: "optional smoothing, never silent" is opt-in repair territory (M2+, BACKLOG); dropping sustained jumps — rejected: tunnels/underpasses are legitimate (#54), only bounces are physically impossible.
- **Risks identified:** haversine via libm trig is not bit-specified cross-platform → decision values only compare against thresholds (ulp-safe in practice) and reported speeds round to 0.1 before serialization; noted for the M3 parity suite.
- **Contract check:** forensic never drops (ADR-0003); every drop counted in provenance; virtual exemption itself provenance'd.
- **Final decision:** APPROVE

## Dependencies
- **Depends on:** F7 · **Depended on by:** F13 (repair), F15 (HR/power gates reuse the pattern)

## Related
- Implementation: [../implementation/f10-gps-plausibility.md](../implementation/f10-gps-plausibility.md)
