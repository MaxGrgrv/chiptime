# Feature: F33 — Errors, messages, and the frame reader for TypeScript

> Status: DONE
>
> **Scope reduced during critique.** This spec originally covered frames *and* decode (~1,600 lines
> of Python). It was split: F33 is the frame layer, F34 is the decoder. See the assessment below.

## Purpose

Make the TypeScript implementation read FIT bytes at the wire level.

`iterFrames` is a public entry point in its own right — the forensics view, `chiptime inspect`'s
data source — so this feature ships a capability rather than scaffolding. It ports `errors.py`,
`message.py` and `frames.py`, and stands up the machinery that makes the decoder possible:
CRC, headers, definition and data framing, and the resync scanner.

It is the first feature where **TypeScript consumes the corpus**. Everything before this was gated
by vectors generated from CPython; from here the shared `corpus/cases/*/input.fit` files are the
input, which is what ADR-0001 was written for.

## Context Check
- [x] `docs/PRD.md` — §6.1 (decode is "incapable of crashing on hostile input"; defects are values,
      not exceptions), the parser behavior contract
- [x] `docs/INDEX.md` — mirrors the frame half of F3; F31/F32 supply canonical, numeric, profile
- [x] `docs/architecture/OVERVIEW.md` — `errors` is a leaf; `frames` sits under `decode`
- [x] `docs/dependencies/DEPENDENCY_MAP.md` — `frames -> errors, profile.base_types`
- [x] `docs/edge-case-taxonomy.md` — items below
- [x] No duplication: field decoding is F34, mode/recovery policy is F35, semantics F36

## Taxonomy Coverage

**No new corpus cases.** Every item below already has one, and that is the point being tested: a
second implementation consuming the same corpus should need no new fixtures (ADR-0001).

| Taxonomy item # | Summary | Corpus case(s) |
|---|---|---|
| 4, 5 | File CRC invalid; header CRC of `0x0000` is legal | `structural/bad-file-crc`, `structural/header-crc-zero` |
| 6 | Invalid header size (not 12 or 14) | `structural/odd-header-size` |
| 7 | `data_size` disagrees with bytes present | `structural/datasize-lies` |
| 8 | Missing `.FIT` magic | `structural/no-magic` |
| 9 | Garbage before the first valid record (Edge 1050) | `structural/preamble-garbage` |
| 10 | Garbage block mid-file, resync | `structural/garbage-block-midfile` |
| 11 | Frame-shift corruption | `protocol/frame-shift-insert` |
| 13 | Trailing junk after the final CRC | `structural/trailing-junk` |
| 19 | Data message with undefined local message type | `structural/undefined-local-resync` |
| 21 | Compressed timestamp *headers* (the header bit; rollover math is F34) | `protocol/compressed-timestamps` |
| — | Definition frames carrying developer field specs; both endiannesses | `protocol/big-endian`, `devfields/*` |

## Requirements

### 1. `js/src/errors.ts` — the leaf everything reports through
1. `Defect`, `Diagnostic`, `ProvenanceEntry` as readonly interfaces plus constructor helpers.
2. `FitError extends Error` with `code`, `detail`, `byteOffset`, `suggestion`, and the six
   subclasses (`NotFitError`, `EmptyFileError`, `HeaderError`, `TruncatedError`,
   `CrcMismatchError`, `ProtocolError`).
3. `instanceof` must work for every subclass. Subclassing `Error` in TypeScript needs the
   `Object.setPrototypeOf` fix-up when targeting anything below ES2015 semantics, and a
   `catch (e) { if (e instanceof TruncatedError) }` that silently fails is worse than no hierarchy.
   Tested explicitly, per subclass.
4. The three code registries — **25 error, 42 warning, 36 provenance codes** — and the
   defect-to-error-class mapping with `defectToError()`.
5. **Registries are transcoded, not hand-copied** (`scripts/gen_codes_ts.py`), following F32's
   precedent: 103 agent-facing strings are data, not protocol constants, and `docs/for-agents.md`
   is generated from the same source. CI regenerates and diffs.

### 2. `js/src/message.ts`
6. `DevFieldOrigin`, `FieldValue`, `Message` mirroring `message.py`. Populated by F34; defined here
   because `frames.ts` and the registries reference the shapes.

### 3. `js/src/frames.ts` — the crash-proof reader
7. `crc16` with the same nibble table, byte-identical results.
8. The frame types: `FileHeader`, `FieldSpec`, `DevFieldSpec`, `DefinitionFrame`, `DataFrame`,
   `CrcFrame`, `SkippedBytes`, `EndOfStream`.
9. `readStream(data, { offset })` as a generator yielding frame events, mirroring `read_stream`.
10. 12- and 14-byte headers including illegal-but-seen variants; both endiannesses; compressed
    timestamp headers; definition frames with developer field specs.
11. **Every read is bounds-checked; every defect is a value, never a throw.** This is the module's
    design promise (PRD §6.1, ADR-0003). `DataView` throws `RangeError` past the end, so each
    access needs an explicit length check — not a `try`/`catch` around the loop, which would
    convert a bounds bug into silent truncation.
12. Resync: `MAX_RESYNCS`, `PREAMBLE_SCAN_LIMIT`, plausible-definition scanning, look-ahead
    validation, `SkippedBytes` accounting. This lives here because `read_stream` owns it in
    Python — and, as the assessment establishes, it is fully exercised by this feature's gate.

### 4. Public surface
13. `iterFrames(src)` exported from `index.ts`, mirroring `iter_frames`. Input is `Uint8Array`
    only; path and stream inputs arrive with intake at F35.
14. **`readStream` takes no mode; `iterFrames` does.** *(Corrected during implementation — the
    original requirement conflated the two.)* `read_stream` in Python has no mode: it reports what
    it finds. But the public `iter_frames` wrapper is not a pass-through — it owns the chained-file
    loop (taxonomy #12), raises the first defect in `strict` with a code-specific suggestion, and
    yields **nothing at all** for a zero-length input because its `while` never runs. Both
    behaviors are observable and both were caught by the corpus gate on its first run.

### 5. The corpus gate
15. `scripts/check_frame_parity.py` runs `iter_frames` and `iterFrames` over **every**
    `corpus/cases/*/input.fit` and diffs a canonical dump: event kind, byte offset, and the
    identifying payload of each frame. Serialized with each side's own canonical JSON (F31), so the
    comparison is byte-level and reuses the determinism contract rather than inventing a diff.
16. **All 72 cases are in scope. There is no skip list** — see the assessment.
17. Fuzz-lite, mirroring the Python gate: truncate a clean corpus input at every byte offset;
    `iterFrames` must never throw, never hang, and must account for every byte.

## Acceptance Criteria
- [ ] Frame-level parity on **all 72** corpus cases, byte-identical dumps
- [ ] The 5 cases that exercise frame-level resync (`container/zip-wrapped`,
      `protocol/frame-shift-insert`, `structural/garbage-block-midfile`,
      `structural/preamble-garbage`, `structural/undefined-local-resync`) produce identical
      `SkippedBytes` accounting — same offsets, same counts
- [ ] `crc16` matches Python over the corpus inputs and a byte-sweep vector set
- [ ] Truncation sweep: no throw, no hang, every byte accounted for
- [ ] `instanceof` works for every `FitError` subclass
- [ ] Code registries regenerate with no diff; all 103 codes match Python exactly
- [ ] `tsc`, Biome, guards, vitest, determinism, pack smoke, all parity gates green
- [ ] Per-mode behavior: **N/A** — `read_stream` has no mode (Requirement 14). Modes arrive at F35

## Public API Impact

**New TypeScript exports**: `iterFrames`, the `FitError` hierarchy, the frame types, `Message` /
`FieldValue` / `DevFieldOrigin` shapes. Nothing published — npm publishing begins at F36.

No Python change, no canonical JSON schema change. New dev tooling: `scripts/gen_codes_ts.py`,
`scripts/check_frame_parity.py`.

## Architectural Placement

**`decode` layer** (`frames.ts`), with `errors.ts` as a leaf. `frames.ts` imports only `errors` and
`profile/base-types` — matching Python exactly.

## Proposed Approach

Port `errors.ts` (with transcoded registries) and `message.ts` first, since `frames.ts` references
both. Then `frames.ts` against the frame-parity gate: generate Python's dump, watch TypeScript
fail, fix TypeScript. Where Python turns out to be the odd one, escalate per ADR-0009 §1 rather
than accommodate.

## Critique & Assessment

_Assessed 2026-08-21. Two claims in the original spec were checked against the actual Python
behavior before assessing. One held; the other was wrong in a way that would have quietly gutted
the gate._

### Finding 1 — the gate was drawn at the wrong layer. **Verified and corrected.**

The original spec scoped its corpus gate to "cases whose Python decode completes without engaging
recovery", deferring the rest to the recovery feature. That reasoning confused two different
things called recovery.

`read_stream` performs frame-level resync **itself**: it scans for the next plausible definition,
accounts for skipped bytes, and emits `SkippedBytes` events, with no help from any layer above.
What the later feature adds is the *API-level mode policy* (strict raises, forensic annotates) and
truncation salvage — neither of which `iter_frames` participates in.

Measured across the corpus:

- `iter_frames` completes on **72 of 72** cases. Zero raise.
- `iter_messages` completes on **72 of 72** cases, 3,213 messages. Zero raise.
- **5 cases exercise frame-level resync** and emit `SkippedBytes`: `container/zip-wrapped`,
  `protocol/frame-shift-insert`, `structural/garbage-block-midfile`, `structural/preamble-garbage`,
  `structural/undefined-local-resync`.

So the proposed skip criterion would have excluded precisely the five most valuable cases — the
ones where the resync scanner is the code under test — and would have shipped Requirement 12's
machinery with no coverage at all. Worse, the criterion was *computed from Python's behavior at run
time*, so a change on the Python side could shrink the gate silently while every check stayed
green.

**Correction:** gate all 72 cases, delete the skip-list mechanism, and assert the `SkippedBytes`
accounting on the five resync cases by name. Applied to Requirements 15–16 and the acceptance
criteria.

### Finding 2 — the feature was too large to critique honestly. **Split.**

At ~1,600 lines of Python across four modules, F33 was three times F32 and four times F31. The
value of this workflow is per-feature critique and verification; one critique pass over 1,600 lines
is where that stops working, and a single 1,900-line TypeScript commit is not reviewable in the way
the rest of this project has been.

The original spec already proposed two internally-gated stages, which is the tell: if the work has
two gates, it has two features. And the first stage is not scaffolding — `iter_frames` is a public
entry point and `chiptime inspect`'s data source, with a complete 72-case gate available before a
single field is decoded.

**Split:** F33 is errors + message + frames (`iterFrames`); **F34 is the decoder**
(`iterMessages`). Everything downstream shifts by one — intake/recovery/CLI to F35, semantics and
npm `0.1.0` to F36, through to F43. The ladder has absorbed a renumber before (F41's catch-up rung)
and nothing past F32 is built, so the cost is a table edit.

### Finding 3 — `include_raw` had no home. **Deferred, deliberately.**

The original Requirement 6 said `FieldValue.raw` is populated "when requested" without saying how
the flag threads. That belongs to F34, which owns field decoding, and to F35, which owns the
`parse()` options object. Removed from this spec rather than half-specified here.

### Alternatives considered
1. *Keep one feature, two commits.* Preserves the ladder and avoids a renumber, but concentrates
   1,600 lines under one critique — the exact thing the split exists to prevent. Rejected.
2. *Split three ways (errors / frames / decode).* `errors.ts` is 103 transcoded codes and six class
   declarations with no behavior of its own and no gate; a feature that cannot be verified
   independently is not a feature. Rejected.
3. *Defer resync to the recovery feature.* Impossible without restructuring: `read_stream` performs
   resync inline, so extracting it would make the TypeScript frame reader structurally different
   from Python's — divergence in the one module whose job is to mirror byte-level behavior.
   Rejected, and Finding 1 removes the motivation anyway.

### What could go wrong at scale
The frame reader is the only module that sees every byte of a hostile file. `MAX_RESYNCS` (64) and
`PREAMBLE_SCAN_LIMIT` (4096) are the anti-hang bounds and must port as-is — a TypeScript resync
loop without them turns a corrupt file into a hang, which for a browser package means a frozen tab
rather than a stack trace. The truncation sweep (Requirement 17) is what proves it.

### Contract check
- **Silent loss** — `SkippedBytes` accounting is the provenance mechanism at this layer, and the
  gate now asserts it byte-for-byte on all five resync cases rather than skipping them.
- **Determinism** — the dump is serialized through F31's canonical JSON, so the comparison inherits
  a contract already proven byte-identical across processes and languages.
- **Sentinels & zero-vs-null** — N/A at the frame layer; frames carry raw bytes, and F34 owns the
  sentinel mapping.
- **Modes** — correctly N/A, and Requirement 14 explains why rather than leaving it blank: adding
  a mode parameter Python does not have would invent a divergence.
- **Errors** — the `FitError` hierarchy and all 103 codes come across; transcoding means they
  cannot drift from the agent-facing contract `docs/for-agents.md` publishes.
- **Corpus** — no new cases, by design. The existing ones now get a second consumer.

### Dependency analysis
`errors.ts` is a leaf; `frames.ts` imports `errors` and `profile/base-types` only. No cycles, and
the layering rule (`decode` never imports `semantics`) is trivially satisfied since semantics does
not exist yet — worth stating because this is the feature where it would first be convenient to
break.

**Blast radius:** total for everything downstream, and loud. A framing bug fails the 72-case gate
immediately rather than surfacing as a strange field value at F34.

### Simplification
The split *is* the simplification. Beyond it, the only requirement examined and kept is the
transcoded code registries: 103 strings could be hand-copied in twenty minutes and would drift on
the first Python edit, and they are a published contract.

### Final decision: **APPROVE** — as split, with Findings 1 and 3 applied above

The corrected gate is stronger than what was proposed (72 cases instead of an ill-defined subset,
with the resync cases explicitly named), the scope is now reviewable, and the deferred item has a
home.

## Dependencies
- **Depends on:** F31 (canonical, numeric), F32 (profile base types), ADR-0003, ADR-0009; F3 in
  Python as the reference
- **Depended on by:** F34 (decoder), F35–F43

## Related
- ADR: [0003](../architecture/adrs/0003-defects-as-values-and-modes.md), [0009](../architecture/adrs/0009-cross-language-parity.md)
- Plan: [../m3-typescript-plan.md](../m3-typescript-plan.md)
- Implementation: `../implementation/f33-js-frames-decode.md` (created by `/implement`)
