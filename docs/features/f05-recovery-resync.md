# Feature: F5 — Recovery: Truncation Salvage + Resynchronization

> Status: DONE

## Purpose
The capability no OSS FIT library has (research gap #1): when corruption hits mid-file, don't stop — classify, scan forward to the next plausible definition frame, account for every skipped byte, and keep decoding. Data on BOTH sides of a corrupt region survives.

## Context Check
- [x] All five context docs reviewed. F3 left explicit `stopped=True` markers where resync belongs.

## Taxonomy Coverage

| Taxonomy item # | Summary | Corpus case(s) |
|---|---|---|
| 9 | Garbage before first valid record (Edge 1050 class) | structural/preamble-garbage |
| 10 | Garbage block mid-file (bad flash sectors) | structural/garbage-block-midfile |
| 19 | Data message with undefined local type → skip + resync | structural/undefined-local-resync |
| 11 | Frame-shift corruption → re-anchor on next definition | protocol/frame-shift-insert |
| 2/3 | Truncation salvage (completed from F3's prefix salvage) | structural/truncated-mid-record (existing) |
| 17 | Bit-flip plausibility hook | (structural detection here; value-level gates in F10/F15) |

## Requirements
1. Frame reader resynchronizes after `FIT_UNDEFINED_LOCAL_TYPE` / `FIT_DEFINITION_INVALID`: byte-scan for the next plausible **definition** frame (taxonomy #11 prescribes definition re-anchoring; data headers are too low-entropy).
2. Plausibility validator for candidate definitions: header bits (bit4 clear), arch ∈ {0,1}, 1–100 fields, every field's base type known and size a positive multiple of it, whole definition in bounds, PLUS one-frame lookahead (the bytes after must themselves start a plausible frame).
3. Preamble garbage: when the stream doesn't start with a plausible header, scan the first 4 KiB for `.FIT` magic and re-anchor the header there, skipping the preamble with provenance.
4. Every skipped span → `SkippedBytes(offset, length, reason)` event → `RESYNC_SKIPPED_BYTES` / `PREAMBLE_GARBAGE_SKIPPED` provenance; `RecoveryReport.bytes_skipped`/`resync_count` populated.
5. Resync bounded (64 attempts) — pathological files degrade to prefix salvage, never hang.
6. Strict mode unchanged: raises at the defect, before any resync continues (generator ordering guarantees this for free).

## Acceptance Criteria
- [x] undefined-local case: records on both sides of the corrupt span decoded
- [x] garbage-block case: decoding resumes after a 40-byte trashed span
- [x] preamble case: header found behind junk; whole file decodes
- [x] all prior 31 cases still green (resync must not disturb clean parsing)

## Public API Impact
None (behavioral). New provenance codes: RESYNC_SKIPPED_BYTES, PREAMBLE_GARBAGE_SKIPPED.

## Architectural Placement
decode layer (`frames.py` owns the scan — it owns byte-level knowledge); `_api` folds SkippedBytes into provenance/recovery.

## Proposed Approach
Replace F3's `stopped=True` breaks with scan-and-continue; validator + lookahead as above.

## Critique & Assessment
- **Alternatives considered:** re-anchoring on data frames too (rejected: any byte 0x00–0x0F matches a data header — false-positive resyncs would fabricate garbage records; definitions carry enough structure to validate). Separate recovery.py module (rejected for now: the scan needs frames.py's internals; splitting adds indirection without isolation — revisit if the algorithm grows).
- **Risks identified:** false-positive definition match inside record payload — mitigated by the strict validator + lookahead; frame-shift cases show payload bytes CAN masquerade as data frames (documented honestly; value-plausibility gates in F10/F15 are the second line). O(n²) on hostile input — bounded by resync cap.
- **Simplification opportunities:** none — this is the minimum honest version.
- **Contract check:** every skipped byte counted and provenance'd (#1); resync deterministic (pure byte predicate, no heuristic state) (#2); strict unchanged (#3); honest non-recovery — bytes that don't validate stay skipped, never guessed into records (#8).
- **Final decision:** APPROVE

## Dependencies
- **Depends on:** F3, F4
- **Depended on by:** F10/F15 (plausibility gates flag what resync can't see), F13 (repair)

## Related
- ADR: [0003](../architecture/adrs/0003-defects-as-values-and-modes.md)
- Implementation: [../implementation/f05-recovery-resync.md](../implementation/f05-recovery-resync.md)
