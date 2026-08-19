# Implementation: F3 — Decode Core

> Feature Spec: [../features/f03-decode-core.md](../features/f03-decode-core.md)

## Summary
The crash-proof wire decoder is live: `frames.py` (defect-emitting frame reader), `decode.py` (typed messages: sentinels→null, scale/offset, enums, ISO timestamps, compressed-timestamp rollover, arrays, strings, per-field salvage), `errors.py` (code registry), `result.py` (ParseResult + canonical schema v1 shaping), `_api.py` (`parse`/`iter_frames`/`iter_messages`, mode policy, chained-part loop, strip_pii). Hand-authored core profile verified against fitdecode: **16 messages / 158 fields / 11 enums (134 values), zero mismatches** after the checker caught 13 real memory errors (event enum off-by-two from a missed cad-alert pair, field_description numbering, `polar_electro`).

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| python/src/chiptime/errors.py | Added | FitError hierarchy, Defect/Diagnostic/ProvenanceEntry, code registries |
| python/src/chiptime/profile/{__init__,base_types,core}.py | Added | Base types + sentinels; core profile tables |
| python/src/chiptime/frames.py | Added | Frame reader: headers (12/14/nonstandard), definitions incl. dev specs, compressed headers, CRC frames, truncation defects |
| python/src/chiptime/decode.py | Added | Decoder with anchor state, aggregated salvage provenance, deduped diagnostics |
| python/src/chiptime/message.py | Added | Message/FieldValue/DevFieldOrigin |
| python/src/chiptime/result.py | Added | ParseResult, SourceInfo, RecoveryReport, FitPart, canonical shaping (64-bit→string, bytes→hex) |
| python/src/chiptime/_api.py | Added | parse() policy loop, prefix salvage + estimates, strip_pii, include_unknown, chained parts |
| scripts/check_profile_against_fitdecode.py | Added | ADR-0004 §2 hard gate (baselines group) |
| corpus/tools/build_fit.py | Modified | 9 new seeds; verbatim-bytes string escape hatch |
| corpus/tools/corrupt.py | Modified | fix_file_crc / fix_header_crc ops |
| corpus/tools/gen_all.py | Modified | `--only` no longer shrinks MANIFEST |
| python/tests/test_decode.py, conftest.py | Added | 18 unit tests against the independent fixture writer |

## Corpus Cases Added

18 cases: clean/{ride-smooth,run-basic}; structural/{empty-file, file-crc-bad, header-crc-zero, header-crc-bad, header-size-invalid, data-size-lies-short, truncated-mid-record}; protocol/{local-redefinition, compressed-timestamps, sentinel-values, big-endian, string-edges, array-fields, float-nan-inf, uint64-fields, invalid-base-type}. Taxonomy items covered: 1, 2(prefix), 4, 5, 6, 7, 20, 21, 25, 26, 27, 32, 33, 34, 35 (+64/68 raw material in seeds).

## Key Implementation Decisions
1. **Warnings reuse defect codes** — no `*_IGNORED` aliases; the array (`errors[]` vs `warnings[]`) conveys treatment, the code stays stable for agents.
2. **Field 253 is a timestamp on any message type** (incl. unknown ones) — updates the compressed-timestamp anchor regardless of profile coverage.
3. **Per-field salvage aggregates** — one provenance entry per (definition, field, reason) with a count, plus one data-severity Defect (so strict still rejects), instead of per-record flooding.
4. **Array sentinel tails trimmed, interior nulls kept** (#34); all-invalid arrays → null.
5. **Fixture realism rule** learned via `data-size-lies-short`: header surgery in corpus pipelines must re-fix the CRCs a real device would have written consistently (`fix_header_crc`/`fix_file_crc` ops) — otherwise strict mode trips on the wrong defect.

## Deviations from Spec
- None.

## Lessons Learned
The independent-writer + independent-profile-checker combination caught every planted class of error (13 profile mismatches, one unrealistic fixture, an empty-input control-flow bug). The corpus is doing its job before the recovery layer even exists.

## Post-Implementation Checklist
- [x] Feature spec status DONE · INDEX/DEPENDENCY_MAP/OVERVIEW updated
- [x] 59 tests green (41 unit + 18 conformance); ruff + mypy --strict clean
- [x] Every salvage/skip emits provenance; determinism double-parse enforced per corpus case
- [x] Skills assessed — no updates needed
