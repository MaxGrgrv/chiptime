# Implementation: F4 — Intake

> Feature Spec: [../features/f04-intake.md](../features/f04-intake.md)

## Summary
`intake.py`: bounded unwrap loop (gzip/zip, ≤3 layers; multi-entry zips concatenate into the legal chained form with provenance), FIT-plausibility check, and content sniffing that names the real format (GPX/TCX/HTML/XML/JSON/plain text). `parse()` now front-runs intake, records `source.unwrapped`, converts intake defects per mode, and formalizes trailing junk as `FIT_TRAILING_JUNK` (strict raises; lenient warns). Chained files parse into N parts with per-part CRC handling.

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| python/src/chiptime/intake.py | Added | Unwrap + sniff, defects-as-values |
| python/src/chiptime/_api.py | Modified | Intake integration; early fatal return; FIT_TRAILING_JUNK strict/lenient split |
| python/src/chiptime/errors.py | Modified | Registry: TRAILING_BYTES → FIT_TRAILING_JUNK; ZIP_ENTRIES_CHAINED added |
| corpus/tools/build_fit.py | Modified | Seeds: course_file, workout_file, monitoring_file, summary_only |
| python/tests/test_intake.py | Added | 12 tests: containers, nesting, sniff matrix, chain, junk, routing |

## Corpus Cases Added
13: container/{gzip-wrapped, zip-wrapped, gpx-renamed, tcx-renamed, html-error-page, json-error}; structural/{chained-two-activities, trailing-junk, magic-missing}; routing/{course-file, workout-file, monitoring-file, summary-only-activity}. Taxonomy: 8, 12, 13, 14, 15, 79, 80.

## Key Implementation Decisions
1. `source.sha256`/`size_bytes` describe the **raw input as given** (what's on the user's disk), not the unwrapped bytes — truthful provenance; `unwrapped` records the peeling.
2. Multi-entry zips map onto the existing chained-parts path instead of growing a second multi-file mechanism.
3. Unrecognized non-text bytes are NOT guessed at — they fall through to the frame reader whose defects are more precise.
4. File-type routing needs no allowlist: `file_id.type` enum maps through the profile; unknown types surface as `unknown_N` and still parse (monitoring case proves it).

## Deviations from Spec
- None.

## Lessons Learned
Mapping "zip with several .fit entries" onto chained parsing collapsed what could have been a special-cased API (multi-file results) into the existing `parts` model — chained files and batch exports are now indistinguishable downstream, which is exactly right.

## Post-Implementation Checklist
- [x] Spec DONE · INDEX/OVERVIEW updated (intake module row)
- [x] 84 tests green (31 conformance); ruff + mypy clean
- [x] Unwrapping + entry-chaining recorded (source.unwrapped, provenance)
- [x] Skills assessed — no updates needed
