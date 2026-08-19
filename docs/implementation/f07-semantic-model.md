# Implementation: F7 — Semantic Model

> Feature Spec: [../features/f07-semantic-model.md](../features/f07-semantic-model.md)

## Summary
`model.py` (Activity/Session/Lap/Length/Totals/Records/Stream/Gap/Discrepancy/DeviceInfo/AthleteProfile/Event) + `semantics/build.py`: order-independent two-pass assembly, columnar streams (every record field — native, `field_N`, developer — becomes a stream; None=absent, 0=zero), enhanced-pair merging with disagreement accounting, dev-stream promotion via F6 registry (`running_power` from Stryd with `source="developer:stryd"`), lap/session end times from `start + elapsed` (#50), basic derived totals. Canonical JSON: `parts[].activity` added; record messages fold into streams (lossless, ~10× smaller than row output).

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| python/src/chiptime/model.py | Added | The PRD §7 model, slots dataclasses |
| python/src/chiptime/semantics/{__init__,build}.py | Added | Assembly: bucketing, time-bound assignment, stream building, enhanced merge, derive |
| python/src/chiptime/result.py | Modified | `_activity_dict` serialization; record-message folding |
| python/src/chiptime/_api.py | Modified | Model built for activity parts (post-PII-strip) |
| python/src/chiptime/errors.py | Modified | ENHANCED_PAIR_MERGED / ENHANCED_PAIR_DISAGREES / RECORDS_OUTSIDE_SESSIONS |
| corpus/tools/build_fit.py | Modified | enhanced_pairs seed |
| python/tests/test_semantics.py | Added | 5 model tests |

## Corpus Cases Added
semantics/enhanced-pairs (#28, #61 — 16-bit speed saturation vs enhanced). All 41 prior snapshots regenerated for the schema addition (documented pre-release procedure, ADR-0001).

## Key Implementation Decisions
1. **Records fold into streams in canonical JSON** — lossless because stream assembly consumes *every* record field including unknowns and dev fields; per-record byte offsets are the one loss, and `iter_frames` retains that forensically.
2. Session assignment is single-session-tolerant (all records attach) and containment-based for multisport, with `RECORDS_OUTSIDE_SESSIONS` warning for leftovers — F9 formalizes.
3. `slots=True` models forced a clean bucket-return design in `_assign` (no attribute smuggling) — better than the first draft.
4. Enhanced merge fills base-absent elements from enhanced (fast-descent saturation case) and counts disagreements rather than hiding them.

## Deviations from Spec
- None.

## Lessons Learned
The "streams are the lossless home for record data" decision is what makes folding legal — worth stating in for-agents docs so downstream consumers don't look for record messages.

## Post-Implementation Checklist
- [x] Spec DONE · INDEX/OVERVIEW updated · 112 tests green (42 conformance) · ruff/mypy clean
- [x] Merges/leftovers all provenance'd or warned
- [x] Skills assessed — no updates needed
