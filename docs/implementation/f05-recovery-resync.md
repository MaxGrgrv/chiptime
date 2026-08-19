# Implementation: F5 — Recovery: Resynchronization

> Feature Spec: [../features/f05-recovery-resync.md](../features/f05-recovery-resync.md)

## Summary
The frame reader now resynchronizes instead of stopping: on `FIT_UNDEFINED_LOCAL_TYPE` / `FIT_DEFINITION_INVALID` it scans for the next plausible definition frame (strict validator: reserved-bit, arch, field-triple sanity, size caps, one-frame lookahead), emits `SkippedBytes`, and continues. Preamble garbage before the header is scanned past (4 KiB window, `.FIT` magic re-anchor). `parse()` folds skips into `RESYNC_SKIPPED_BYTES` / `PREAMBLE_GARBAGE_SKIPPED` provenance and populates `bytes_skipped` / `resync_count`. Measured results: undefined-local case salvages **6/6 records around the corrupt span**; a 40-byte flash-trash block loses only 9 of 120 records; 23 bytes of preamble junk lose zero.

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| python/src/chiptime/frames.py | Modified | `_plausible_definition` validator, `_lookahead_ok`, `_find_next_definition`, `_resync` closure, preamble scan, MAX_RESYNCS=64 |
| python/src/chiptime/_api.py | Modified | SkippedBytes → provenance + RecoveryReport counters; resynced defects not double-reported |
| python/src/chiptime/errors.py | Modified | RESYNC_SKIPPED_BYTES / PREAMBLE_GARBAGE_SKIPPED registry entries |
| corpus/tools/build_fit.py | Modified | ride_smooth re-emits its record definition mid-stream (realistic + resync anchor); seeds undefined_local, frame_shift |
| python/tests/test_recovery.py | Added | 5 tests incl. clean-file no-resync guard |
| python/tests/test_decode.py | Modified | F3 stop-behavior test upgraded to F5 resync contract |

## Corpus Cases Added
4: structural/{preamble-garbage, garbage-block-midfile, undefined-local-resync}; protocol/frame-shift-insert. Taxonomy: 9, 10, 11, 17(hook), 19. Cases truncated-mid-record / data-size-lies-short re-based on the grown seed (offsets 3512 / 3469).

## Key Implementation Decisions
1. **Re-anchor on definitions only** (taxonomy #11's prescription): data headers are one low-entropy byte — matching them would fabricate records. The validator demands known base types, positive multiple sizes, ≤2048-byte payloads, and a plausible following frame.
2. **Strict mode needed zero changes**: the generator yields the Defect before the SkippedBytes, so strict raises before any resync is consumed.
3. **Frame-shift honesty**: a shifted region can masquerade as valid-looking bogus messages (our case decodes one phantom `file_id`). These are preserved, not suppressed — value-level plausibility gates (F10/F15) are the second line of defense. Documented in the case notes.
4. `ride_smooth` now re-emits its record definition mid-stream — matching real device behavior and giving mid-file corruption a realistic re-anchor point.

## Deviations from Spec
- None.

## Lessons Learned
Generator ordering (Defect before SkippedBytes) gave strict-mode correctness for free — the ADR-0003 "modes are one policy switch" bet paying off concretely.

## Post-Implementation Checklist
- [x] Spec DONE · INDEX/OVERVIEW updated
- [x] 93 tests green (35 conformance); ruff + mypy clean
- [x] Every skipped byte counted in provenance + RecoveryReport
- [x] Skills assessed — no updates needed
