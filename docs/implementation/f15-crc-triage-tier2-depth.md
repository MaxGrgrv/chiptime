# Implementation: F15 — CRC Triage + Tier-2 Depth Batch

> Feature Spec: [../features/f15-crc-triage-tier2-depth.md](../features/f15-crc-triage-tier2-depth.md)

## Summary
Frame reader CRC triage (zeroed-trailer = unterminated write / co-occurring damage = storage class / clean decode = in-place or lazy-encoder — fitparse #9); decode-layer compressed_speed_distance expansion with 12-bit modular accumulation and accumulated_power uint32 unwrap (both provenance-aggregated); event.data → timer_trigger subfield (feeding auto_pause gap evidence); sensor/distance/pool/lap flag sets in reconcile — everything flagged, nothing edited.

## Files Changed
| File | Change Type | Description |
|------|------------|-------------|
| python/src/chiptime/frames.py | Modified | CRC mismatch triage classes in defect detail |
| python/src/chiptime/decode.py | Modified | `_expand_record_components`, `_resolve_event_subfield`, accumulator state |
| python/src/chiptime/semantics/reconcile.py | Modified | sensor_flags / swim_checks / lap_checks |
| python/src/chiptime/semantics/build.py | Modified | Hook the three check sets |
| python/src/chiptime/errors.py | Modified | 11 new warning codes |
| corpus/tools/build_fit.py | Modified | 6 seeds |
| python/tests/test_tier2_depth.py | Added | 8 tests |

## Corpus Cases Added
7: structural/file-crc-zeroed (#4), protocol/{compressed-speed-distance (#29), accumulator-rollover (#30), event-subfields (#31)}, sensors/hr-power-distance-anomalies (#59/62/63), swim/pool-lengths (#73), reconcile/zero-duration-lap (#94). **Census: 63 cases.**

## Key Implementation Decisions
1. HR 250 bpm and 4 kW samples stay in the streams — flags only; dropping physiology is an opt-in repair (BACKLOG), sprints are real until proven otherwise.
2. csd expansion synthesizes speed/distance only when the modern fields are absent — never fights real streams.
3. Pool-size implausibility phrased exactly as the taxonomy demands: "flaggable, not fixable".

## Post-Implementation Checklist
- [x] Spec DONE · INDEX updated · 199 tests green (63 conformance) · ruff/mypy clean
- [x] Expansions provenance'd; flags stable-coded; zero silent edits
