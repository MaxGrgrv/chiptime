# Feature: F33 — Frames and decode core for TypeScript

> Status: DRAFT

## Purpose

Make the TypeScript implementation read FIT bytes.

This is the largest feature in M3 and the first one that touches a file. It ports four Python
modules — `errors.py`, `message.py`, `frames.py`, `decode.py` (~1,600 lines) — producing
`iterFrames` (lossless wire-level events) and `iterMessages` (profile-applied messages), which are
two of the three public entry points the Python package exposes.

It is also the first feature where **TypeScript consumes the corpus**. Everything before this was
gated by vectors generated from CPython; from here the shared `corpus/cases/*/input.fit` files are
the input, exactly as ADR-0001 intended.

## Context Check
- [x] `docs/PRD.md` — §6.1 (decode is "incapable of crashing on hostile input"; defects are values,
      not exceptions), §6.2, the parser behavior contract
- [x] `docs/INDEX.md` — mirrors F3 (decode core), F6 (developer fields), F22 (ecosystem hardening);
      F31/F32 supply canonical, numeric and profile
- [x] `docs/architecture/OVERVIEW.md` — `decode` never imports `semantics`; `errors` is a leaf
- [x] `docs/dependencies/DEPENDENCY_MAP.md` — `decode -> frames, message, profile, errors`
- [x] `docs/edge-case-taxonomy.md` — items below
- [x] No duplication: recovery/resync policy is F34, semantics is F35

## Taxonomy Coverage

The behaviors ported here are the ones F3, F6 and F22 established in Python. Corpus cases already
exist for every item — **this feature adds none**, it makes the TypeScript side produce identical
output for the ones we have. That is the ADR-0001 promise finally being exercised: the second
implementation should need no new fixtures.

| Taxonomy item # | Summary | Corpus case(s) |
|---|---|---|
| 19 | Data message with undefined local message type | `protocol/local-redefinition`, `protocol/frame-shift-insert` |
| 21 | Compressed timestamp headers, rollover, missing anchor | `protocol/compressed-timestamps` |
| 22a–d | Developer fields: missing description, null names, reused index, late description, no `developer_data_id`, known vendors | all six `devfields/*` |
| 26 | Sentinel invalid values decoded as literals | `protocol/sentinel-values`, `protocol/float-sentinel-vs-nan` |
| 27 | Scale/offset application, semicircles | `protocol/big-endian`, `clean/ride-smooth` |
| 28 | `enhanced_` field pairs | `clean/ride-smooth` (reconciliation itself is F35) |
| 35 | Float NaN/Infinity | `protocol/float-nan-inf` |
| 43 | 64-bit fields | `protocol/uint64-fields` |
| 53 | String edge cases, multi-string arrays | `protocol/string-edges`, `protocol/multi-string-arrays` |
| — | Big-endian definitions, array fields, unknown enums, invalid base types, accumulator rollover, compressed speed/distance | remaining `protocol/*` |

Contract #6 (unknown ≠ invalid) is exercised throughout: `protocol/unknown-enum-values`,
`protocol/invalid-base-type`.

## Requirements

### 1. `js/src/errors.ts` — the leaf everything reports through
1. `Defect`, `Diagnostic`, `ProvenanceEntry` as plain readonly interfaces plus constructor helpers,
   mirroring the frozen dataclasses.
2. `FitError` extending `Error` with `code`, `detail`, `byteOffset`, `suggestion`, and the six
   subclasses (`NotFitError`, `EmptyFileError`, `HeaderError`, `TruncatedError`,
   `CrcMismatchError`, `ProtocolError`).
3. The three code registries — **25 error, 42 warning, 36 provenance codes** — and the
   defect-to-error-class mapping, plus `defectToError()`.
4. **The registries are transcoded, not hand-copied** (the F32 pattern): `scripts/gen_codes_ts.py`
   emits them from `chiptime.errors`, and CI regenerates and diffs. 103 strings hand-copied would
   drift on the first Python edit, and these strings are an agent-facing contract
   (`docs/for-agents.md` is generated from them).
5. `instanceof` must work across the subclass hierarchy — `Error` subclassing in TypeScript
   requires the prototype fix-up, and a `catch (e) { if (e instanceof TruncatedError) }` that
   silently fails is worse than no hierarchy at all. Tested explicitly.

### 2. `js/src/message.ts`
6. `DevFieldOrigin`, `FieldValue`, `Message` mirroring `message.py`. `FieldValue.value` carries the
   scaled, sentinel-resolved value; `raw` the wire value when requested; `units`; `developer`.

### 3. `js/src/frames.ts` — the crash-proof reader
7. `crc16` with the same nibble table, byte-for-byte identical results.
8. The seven frame types: `FileHeader`, `FieldSpec`, `DevFieldSpec`, `DefinitionFrame`,
   `DataFrame`, `CrcFrame`, `SkippedBytes`, `EndOfStream`.
9. `readStream(data, { offset })` as a generator yielding frame events, mirroring `read_stream`.
10. 12- and 14-byte headers including illegal-but-seen variants; both endiannesses; compressed
    timestamp headers; definition frames with developer field specs.
11. **Every read is bounds-checked and every defect is a value, never a throw.** This is the
    module's whole design promise (PRD §6.1) and the F32 `BigInt(NaN)` crash is the cautionary
    precedent: a `DataView` read past the end throws `RangeError`, so every access needs an
    explicit length check rather than a try/catch around the loop.
12. Resync scaffolding — `MAX_RESYNCS`, `PREAMBLE_SCAN_LIMIT`, plausible-definition scanning,
    look-ahead validation — ported as-is. The *policy* that decides when to resync is F34; the
    machinery lives here because `read_stream` owns it in Python.

### 4. `js/src/decode.ts` — frames to messages
13. `civilFromUnix` (Hinnant's algorithm, integer-only) and the two timestamp formatters. **`Date`
    is not used** (ADR-0009 §5); `floorDiv`/`divmod` from `numeric.ts` supply Python's floor
    semantics on the negative branch.
14. The `Decoder` class: field plans, base-type element decoding, sentinels to null, scale/offset,
    enum resolution, strings (including multi-string arrays and embedded NULs), arrays,
    compressed timestamps with rollover, and `finish()`.
15. Developer fields: description resolution including late descriptions, reused indices, null
    names, missing `developer_data_id`, and vendor promotion through `profile/registry.ts`.
16. Component expansion (`record` components, `hr` `event_timestamp_12`, compressed speed/distance),
    `timestamp16` merging, accumulator rollover, pedal balance, product resolution, event subfields.
17. 64-bit fields decode through `BigInt` and reach the shaping layer as such (ADR-0009 §4).
18. `_sanitize_field_name`'s regex behavior must match: `[^a-z0-9]+` collapsing, in a language whose
    regex engine differs from Python's on Unicode classes. ASCII-only here, but pinned by tests.

### 5. Public surface
19. `iterFrames(src, { mode })` and `iterMessages(src, { mode })` exported from `index.ts`,
    mirroring `iter_frames` / `iter_messages`.
20. Input is `Uint8Array` only at this stage; path and stream inputs arrive with intake at F34.
21. Mode is accepted and threaded, but only `strict` differs observably here (first defect raises);
    the full three-mode policy is F34's, where recovery gives `forensic` something to do.

### 6. The first corpus gate
22. `scripts/check_decode_parity.py` runs both implementations over every `corpus/cases/*/input.fit`
    and diffs a canonical dump. Two stages, both required:
    - **frames**: `iter_frames` vs `iterFrames` — event kind, offset, and payload-identifying fields
    - **messages**: `iter_messages` vs `iterMessages` — message number, name, and every field's
      value, raw, units and developer origin
23. The dump is serialized with each side's own canonical JSON (F31), so the comparison is
    byte-level and reuses the determinism contract rather than inventing a diff format.
24. Scope: cases whose Python decode completes **without engaging recovery**. Cases that need
    resync or truncation salvage are gated at F34 when TypeScript has the policy to match.
    The script reports which cases it skipped and why — a silent subset would read as full coverage.

## Acceptance Criteria
- [ ] Frame-level parity on every in-scope corpus case, byte-identical dumps
- [ ] Message-level parity on every in-scope corpus case, byte-identical dumps
- [ ] The skipped set is reported by name and count, and every skip has a stated reason
- [ ] `crc16` matches Python for the corpus inputs and for a byte-sweep vector set
- [ ] No input causes a throw in lenient mode — including the deliberately hostile corpus cases and
      a truncation sweep over a clean file (fuzz-lite, mirroring the Python gate)
- [ ] `strict` raises the same error class and code as Python for the cases where Python raises
- [ ] `instanceof` works for every `FitError` subclass
- [ ] 64-bit fields survive as `BigInt` without precision loss
- [ ] Code registries regenerate with no diff; all 103 codes match Python exactly
- [ ] `tsc`, Biome, guards, vitest, determinism, pack smoke, and all parity gates green
- [ ] Per-mode behavior: `strict` raises on first defect; `lenient`/`forensic` collect. Recovery
      differences between the two arrive at F34 and are stated as out of scope here

## Public API Impact

**New TypeScript exports**: `iterFrames`, `iterMessages`, the `FitError` hierarchy, `Message`,
`FieldValue`, `DevFieldOrigin`, and the frame types. This is the first release-shaped surface, but
nothing is published — npm publishing begins at F35 per the release plan.

No Python change. No canonical JSON schema change: `parse()` and its output shape arrive at F34/F35.

New dev tooling: `scripts/gen_codes_ts.py`, `scripts/check_decode_parity.py`.

## Architectural Placement

**`decode` layer**, with `errors` as a leaf. `js/src/decode.ts` imports `frames`, `message`,
`profile`, `errors` — and never `semantics`, which does not exist yet and must not when it does.
The layering rule is identical to Python's and is worth stating because this is the feature where
it would first be convenient to break.

## Proposed Approach

Ported in two internally-gated stages, because a 1,600-line port with one gate at the end is a
debugging trap:

**Stage A — errors, message, frames.** Ends at frame-level parity. `iter_frames` already exists in
Python, so the gate is available before a single field is decoded, and a framing bug surfaces as a
framing diff rather than as a mysterious field value 900 lines later.

**Stage B — decode.** Ends at message-level parity.

Within each stage the F31/F32 pattern holds: generate the expectation from CPython, watch it fail,
fix TypeScript. Where Python turns out to be the odd one, escalate per ADR-0009 §1 rather than
accommodate.

The code registries follow F32's transcoding precedent rather than F31's hand-porting one, because
103 agent-facing strings are data, not protocol constants — the same reasoning that made
`base-types.ts` hand-written and `generated.ts` transcoded.

## Critique & Assessment
_To be filled in by `/critique`. The size is the main thing to challenge: is the two-stage split
sufficient, or should this be two features? And is "cases that decode without recovery" a coherent
gate, or does it carve the corpus along a line that hides something?_
- **Alternatives considered:** _..._
- **Risks identified:** _..._
- **Simplification opportunities:** _..._
- **Contract check (silent loss / determinism / provenance / sentinels):** _..._
- **Final decision:** _pending_

## Dependencies
- **Depends on:** F31 (canonical, numeric), F32 (profile tables), and in Python F3/F6/F22 as the
  reference implementation; ADR-0003 (defects as values), ADR-0009
- **Depended on by:** F34 (intake, recovery, result shaping), F35–F42

## Related
- ADR: [0003](../architecture/adrs/0003-defects-as-values-and-modes.md), [0009](../architecture/adrs/0009-cross-language-parity.md)
- Plan: [../m3-typescript-plan.md](../m3-typescript-plan.md)
- Implementation: `../implementation/f33-js-frames-decode.md` (created by `/implement`)
