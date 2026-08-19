# Implementation: F12 — FIT Encoder

> Feature Spec: [../features/f12-encoder.md](../features/f12-encoder.md)

## Summary
`chiptime/encode.py` per ADR-0006: canonical little-endian wire form, shape-keyed local-slot manager with deterministic round-robin eviction, both CRCs, full developer-field sections (definition dev bit + metadata-matched re-packing), compressed-timestamp materialization as explicit field 253. Producers: `encodable_from_message` (lossless, unknown-inclusive) and `encodable_from_profile` (reverse-scaled synthesis for repair). `Message.wire` retained from decode.

## Files Changed
| File | Change Type | Description |
|------|------------|-------------|
| python/src/chiptime/encode.py | Added | Encoder + two producers + typed EncodeError |
| python/src/chiptime/message.py | Modified | `Message.wire` (ADR-0006 §4) |
| python/src/chiptime/decode.py | Modified | wire retention |
| python/tests/test_encode.py | Added | 13 tests: round trips ×6 seeds, strict-cleanliness, determinism, synthesis, slot eviction, typed errors |

## Corpus Cases Added
None — encoding is not parse behavior (spec rationale); the round-trip property protects decode behaviors transitively. F13's repair cases will exercise this end-to-end.

## Key Implementation Decisions
1. **Dev fields align by origin key** (`developer_data_index`, `field_definition_number`) — never by dict order; resolved dev values re-pack from raw via size-driven packing.
2. Profile-name lookup precedes the `field_N` fallback — `field_description.field_definition_number` is a real profile field name that a prefix check misparsed (caught by round-trip test).
3. Strict-clean contract refined: re-encoded files must raise nothing and introduce no NEW warning class — semantic warnings that describe the data itself legitimately persist.

## Deviations from Spec
- None.

## Lessons Learned
Round-trip testing found two genuine bugs (dev-section absence, name-collision) before any repair code existed — the property is the encoder's real spec.

## Post-Implementation Checklist
- [x] Spec DONE · INDEX/OVERVIEW updated · 170 tests green · ruff/mypy clean (exit codes checked)
- [x] Encoder deterministic; typed errors; no silent behavior
- [x] Skills assessed — no updates needed
