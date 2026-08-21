# Implementation: F33 — Errors, messages, and the frame reader for TypeScript

> Feature Spec: [../features/f33-js-frames-decode.md](../features/f33-js-frames-decode.md)
> Plan: [../m3-typescript-plan.md](../m3-typescript-plan.md) · Contract: [ADR-0009](../architecture/adrs/0009-cross-language-parity.md)

## Summary

TypeScript reads FIT bytes. `iterFrames` produces the same 3,704 frame events as Python across all
72 corpus cases, byte-identically — including the five that exercise frame-level resync.

This is the first feature where the shared corpus is the input rather than vectors generated from
CPython. ADR-0001 predicted a second implementation would need no new fixtures; it needed none.

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `js/src/codes.ts` | Added (generated) | 25 error, 42 warning, 36 provenance codes + defect→class map |
| `js/src/errors.ts` | Added | `FitError` hierarchy, `Defect`/`Diagnostic`/`ProvenanceEntry`, `defectToError` |
| `js/src/message.ts` | Added | `DevFieldOrigin`, `FieldValue`, `Message` shapes (populated at F34) |
| `js/src/frames.ts` | Added | `crc16`, the frame types, `readStream`, the resync scanner |
| `js/src/api.ts` | Added | `iterFrames` — the chained-file loop and mode policy |
| `js/src/index.ts` | Modified | Root surface mirrors Python's `__all__`; submodules reached via subpath exports |
| `js/package.json` | Modified | Subpath exports for `canonical`, `errors`, `frames`, `message`, `profile` |
| `js/test/frames.test.ts` | Added | 53 tests: CRC vectors, `instanceof`, chaining, hostile input |
| `js/test/vectors/crc16.json` | Added | 34 CRC vectors from CPython |
| `js/biome.json` | Modified | Ignores `src/codes.ts` alongside the generated profile |
| `js/scripts/smoke.sh` | Modified | Imports through the subpath exports; asserts `iterFrames` round-trips |
| `scripts/gen_codes_ts.py` | Added | Transcodes the registries |
| `scripts/check_frame_parity.py` | Added | The 72-case frame gate |
| `scripts/gen_parity_vectors.py` | Modified | Emits `crc16.json` |
| `.github/workflows/ci.yml`, `.githooks/pre-push` | Modified | Code-registry staleness + frame parity |

## Corpus Cases Added

**None, by design** — and this is the feature that tests whether that promise holds. Every taxonomy
item in the spec already had a case from F3/F6/F22; the TypeScript reader consumes them unchanged.
The corpus was the contract on paper since ADR-0001; it is now the contract in practice.

## Key Implementation Decisions

1. **`kind` discriminants on the frame types.** Python dispatches on class via `isinstance`;
   TypeScript needs a tag it can narrow on. This is the one structural difference from the Python
   types, and the parity dumper maps `kind` back to the class names so the comparison is unaffected.

2. **`u8()` returns `data[i] ?? 0` rather than asserting non-null.** Every call site bounds-checks
   first, exactly as Python does (where the same read would raise `IndexError`), so the fallback is
   unreachable. It is chosen deliberately over `!`: if a bounds check were ever wrong, this module
   must still not throw, and a spurious `0` cannot spin because position always advances or the
   loop breaks.

3. **`payload` is a `subarray`, not a copy.** Python's slice copies; a view is cheaper and the
   buffer outlives the frames anyway. Nothing mutates the input.

4. **The suggestion table lives in `api.ts`, not the generated `codes.ts`.** It belongs to the API
   boundary that raises, not to the registry that names things — which is where Python keeps it,
   for the same reason.

## Deviations from Spec

1. **Requirement 14 was wrong, and the corpus gate proved it on its first run.** The spec said
   "mode is not a parameter here" because `read_stream` takes none. True of `read_stream`, false of
   `iter_frames` — which is not a pass-through. It owns the chained-file loop, raises in `strict`
   with a code-specific suggestion, and yields **nothing at all** for a zero-length input because
   its `while offset < len(data)` never runs.

   Both showed up as the only two failing cases out of 72: `structural/chained-two-activities`
   (TypeScript stopped after the first stream) and `structural/empty-file` (TypeScript emitted a
   `FIT_EMPTY` defect where Python emits nothing). Requirement 14 has been rewritten to state the
   distinction rather than paper over it.

   The empty-file behavior is worth keeping in mind for F35: reporting an empty file is `parse()`'s
   job (taxonomy #1), and the frame layer is deliberately silent about it.

2. **Biome's lint caught two things worth taking.** `big ? false : true` is `!big`, and the two CRC
   functions reassigned their parameters — legal, matching Python, and clearer with a local. Neither
   changed behavior; both were adopted rather than suppressed.

### Fixed during `/verify`

3. **The package root was exporting names Python keeps in submodules.** `index.ts` surfaced
   `crc16`, `dumps`, `formatNumber`, `MAX_SAFE_INT`, `CanonicalizationError`, `defectToError` and
   the three code registries — none of which are in `chiptime/__init__.py`'s `__all__`. Python
   reaches them as `chiptime.canonical.dumps`, `chiptime.frames.crc16`,
   `chiptime.errors.ERROR_CODES`.

   Fixed by mirroring Python's module reachability rather than flattening it: the package now
   declares **subpath exports** (`chiptime/canonical`, `chiptime/errors`, `chiptime/frames`,
   `chiptime/message`, `chiptime/profile`), and the root exports exactly the subset of Python's
   `__all__` that exists so far — the seven `FitError` classes, `iterFrames`, and the `Mode` type.

   This is the **third** time the twin-surface check has fired, and the third time the divergence
   was a convenience: `dumpsText` at F31, the vendor-registry re-export at F32, and now nine names
   hoisted to the root. None was wrong code. All three were a second way to say what Python says
   one way — exactly the drift that accumulates when nothing looks for it. This fix is structural
   rather than a deletion, so it should stop the class rather than the instance.

## Lessons Learned

- **70 of 72 on the first run, and the two failures were both in the wrapper.** The frame reader —
  ~600 lines of bit manipulation, bounds checks and a resync scanner — was correct on the first
  attempt. What was wrong was the thin function above it, because the spec had described the
  *inner* function's contract and named the *outer* one. The lesson is not "ports are easy"; it is
  that a spec written from the module you are porting can still misdescribe the API you are
  exposing, and only an end-to-end gate catches that.

- **The corpus paid off exactly as ADR-0001 predicted.** No new fixtures, no new expected outputs,
  no judgment calls about what "correct" means — 72 inputs and a byte comparison. Every earlier
  feature had to *generate* its expectation from CPython; this one just read files that were
  already committed.

- **Comparing through canonical JSON was the right call.** Both sides serialize their event dump
  with their own `dumps()`, so the comparison inherits a contract already proven byte-identical
  across processes and languages, rather than inventing a second notion of sameness that would
  itself need testing.

- **The truncation sweep is cheap and belongs everywhere.** Every cut point of a real file, drained
  through the reader, asserting no throw: 108 ms for the whole suite. `DataView` throws
  `RangeError` past the end, so this is the test that proves the bounds checks exist rather than
  trusting that they do.

## Post-Implementation Checklist
- [x] Feature spec status updated to DONE
- [x] INDEX.md updated
- [x] DEPENDENCY_MAP.md updated
- [x] Architecture docs updated (OVERVIEW frame-layer rows)
- [x] All new behavior covered by unit tests (351 total) and the 72-case corpus gate
- [x] Every new drop/repair/reinterpretation emits provenance — `SkippedBytes` accounting is the
      mechanism at this layer, and the gate asserts it byte-for-byte on all five resync cases
- [x] Determinism verified (canonical-JSON dumps identical; cross-process hash unchanged)
- [ ] Skills assessed and updated (`/post-impl-review`)
