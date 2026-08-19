# Feature: F4 — Intake: Sniffing, Unwrapping, Chaining, Routing

> Status: DONE

## Purpose
Everything before frame decoding: recognize what the bytes actually are (taxonomy #15's "download-gone-wrong" class), unwrap containers transparently (#14), formalize chained files (#12) and trailing junk (#13), route by `file_id.type` (#80), and accept summary-only activities (#79).

## Context Check
- [x] All five context docs reviewed; no duplication (frame reader already handles #1/#8 partially).

## Taxonomy Coverage

| Taxonomy item # | Summary | Corpus case(s) |
|---|---|---|
| 14 | zip/gz wrapped FIT | container/gzip-wrapped, container/zip-wrapped |
| 15 | GPX/TCX/JSON/HTML saved as .fit | container/{gpx,tcx,html,json}-renamed |
| 12 | Chained FIT files | structural/chained-two-activities |
| 13 | Trailing junk after final CRC | structural/trailing-junk |
| 8 | Missing .FIT magic, rest valid | structural/magic-missing |
| 80 | Route on file_id.type | routing/{course-file,workout-file,monitoring-file} |
| 79 | Summary-only activity (0 records) | routing/summary-only-activity |

## Requirements
1. `intake.unwrap(bytes)` loop (≤3 layers): gzip magic → decompress; zip magic → extract `.fit` entries (multiple entries concatenate into the legal chained form, with provenance); failures → typed defects.
2. Content sniffing for non-FIT: XML (GPX / TCX / HTML / generic), JSON, generic text → fatal `NOT_FIT_FORMAT` whose detail names the format ("content is GPX (XML with <gpx> root)").
3. Trailing junk becomes defect `FIT_TRAILING_JUNK`: strict raises; lenient/forensic warn (replaces the ad-hoc TRAILING_BYTES code).
4. Chained files: every stream after the first parsed as its own part; per-part CRC defects handled identically (never stop at first CRC — #12).
5. `source.unwrapped` records the unwrap path (["gzip"] / ["zip"] / nested).

## Acceptance Criteria
- [x] 12 new corpus cases green in all three modes
- [x] NOT_FIT detail strings name the sniffed format
- [x] Unwrap loop bounded; a zip-of-gzip-of-fit works

## Public API Impact
None beyond behavior — `parse()` signature unchanged. Registry: `TRAILING_BYTES` removed, `FIT_TRAILING_JUNK` used in both errors[] (strict) and warnings[] (lenient).

## Architectural Placement
intake layer (`chiptime/intake.py`); `_api.parse` calls it before frame reading.

## Proposed Approach
Magic-byte dispatch, then FIT-plausibility check (size byte + magic), then text sniffing; unrecognized bytes still go to the frame reader (its defects are more precise than a guess).

## Critique & Assessment
- **Alternatives considered:** sniffing inside frames.py (rejected: layering — frames must stay pure wire); rejecting multi-entry zips (rejected: GC exports and batch zips are real; concatenation maps them onto the chained-file path we already have).
- **Risks identified:** zip-bomb / deep nesting → unwrap loop hard-capped at 3 layers, decompressed size not re-checked (acceptable: parse is memory-bounded by input; noted for a future guard). Sniffing false-positives on FIT files whose first byte happens to be `<` — impossible: FIT plausibility (header size byte + magic) is checked first.
- **Simplification opportunities:** CSV sniffing dropped — generic "text" answer is equally actionable.
- **Contract check:** unwrapping recorded in `source.unwrapped` + provenance for zip-concatenation (nothing silent); NOT_FIT errors carry code + looks-like detail + suggestion; determinism unaffected (fixed-timestamp zip/gzip in corpus only).
- **Final decision:** APPROVE

## Dependencies
- **Depends on:** F3
- **Depended on by:** F5 (recovery interacts with per-part boundaries), F13 (repair reads intake output)

## Related
- Implementation: [../implementation/f04-intake.md](../implementation/f04-intake.md)
