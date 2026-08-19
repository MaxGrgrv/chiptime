# Implementation: F6 — Developer Fields

> Feature Spec: [../features/f06-developer-fields.md](../features/f06-developer-fields.md)

## Summary
Full #22 resolution: `developer_data_id`/`field_description` state tracking, per-description decoding (base type, scale/offset, units, definition-endianness), sanitized names with deterministic collision suffixes, synthesized `dev_{idx}_{num}` fallback that preserves raw data, **late-description back-fill at finish()** with provenance, index-reuse forward semantics, and the vendor registry (Stryd/greenTEG/Moxy seeds) stamping `DevFieldOrigin.canonical_name` for F7 stream promotion.

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| python/src/chiptime/decode.py | Modified | `_DevDesc`, dev metadata capture (206/207), `_resolve_dev`, back-fill in finish(), `_sanitize_field_name` |
| python/src/chiptime/profile/registry.py | Added | (vendor, field name) → canonical stream name/units |
| python/src/chiptime/profile/core.py | Modified | manufacturer enum + moxy(76), greenteg(303) |
| python/src/chiptime/message.py | Modified | `DevFieldOrigin.canonical_name` |
| python/src/chiptime/result.py | Modified | canonical JSON `developer` object gains canonical_name |
| python/src/chiptime/_api.py | Modified | uses `finish()`-rebuilt message list (back-fill fix) |
| python/src/chiptime/errors.py | Modified | DEV_* warning + provenance codes |
| corpus/tools/build_fit.py | Modified | 6 dev-field seeds |
| python/tests/test_devfields.py | Added | 7 tests incl. streaming-vs-batch back-fill contrast |

## Corpus Cases Added
6 in `devfields/`: stryd-known-vendor, missing-field-description, no-developer-data-id, null-field-name, late-field-description, dev-index-reused. All Tier-1 (#22).

## Key Implementation Decisions
1. **Vendor identity = developer_data_id.manufacturer_id** (stable), not application UUID (varies per build). Registry keys on (manufacturer name, normalized field name).
2. **Back-fill only in batch mode**: `finish()` rebuilds messages whose dev fields resolved late; streaming `iter_messages` keeps placeholders (documented, tested) — streaming can't rewrite the past.
3. Dev-field payloads follow the *definition's* endianness — passed through to resolution (easy to get wrong; test-locked via big-endian machinery from F3).
4. `parse()` now takes its message list from `finish()` — found via failing test: the back-fill was rebuilding a list nobody read.

## Deviations from Spec
- None.

## Lessons Learned
Two planted-by-reality bugs (stale message list, seed string truncation silently renaming "Core Temperature" → "core_te") were both caught by behavior-level tests before any corpus snapshot existed — write the probe test first, snapshot after.

## Post-Implementation Checklist
- [x] Spec DONE · INDEX updated · 106 tests green (41 conformance) · ruff/mypy clean
- [x] Synthesis/back-fill/reuse all carry warnings or provenance
- [x] Skills assessed — no updates needed
