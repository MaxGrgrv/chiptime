# Feature: F35 — Intake, inflate, recovery and `parse()` for TypeScript

> Status: DONE

## Purpose

Give TypeScript the one call everything else is a detail of: `parse()`.

Container unwrapping, content sniffing, the three-mode policy, chained-part assembly, PII
stripping, recovery reporting, and canonical JSON shaping — `intake.py`, the `parse()` half of
`_api.py`, and `result.py`, plus a zero-dependency `inflate.ts` that has no Python counterpart
because Python has `gzip` and `zipfile` in its stdlib and JavaScript has neither synchronously.

This is the feature where the TypeScript output first becomes a **`chiptime_schema: 1` document**
that can be compared against the committed corpus snapshots.

## Context Check
- [x] `docs/PRD.md` — §6.1 (intake before decode; recovery wraps decode), §7.2 (the `parse` surface),
      §7.5 (the canonical JSON shape), contract #1 (provenance), #3 (three modes), #10 (privacy)
- [x] `docs/INDEX.md` — mirrors F4 (intake), F5 (recovery), F11 (result/API), F15 (CRC triage)
- [x] `docs/architecture/OVERVIEW.md` — `_api -> intake, frames, decode, semantics, result, errors`;
      `result -> canonical, errors, message`
- [x] `docs/dependencies/DEPENDENCY_MAP.md` — F34 supplies the decoder; runtime deps stay zero
- [x] `docs/edge-case-taxonomy.md` — items below
- [x] No duplication: the semantic model is F36; the CLI is proposed as its own feature (below)

## Taxonomy Coverage

**No new corpus cases.** Third feature running: the fixtures exist and the second implementation
consumes them unchanged.

| Taxonomy item # | Summary | Corpus case(s) |
|---|---|---|
| 1 | Zero-byte / near-empty file → `FIT_EMPTY`, no partial output | `structural/empty-file` |
| 12 | Chained FIT files emitted as multiple parts | `structural/chained-two-activities` |
| 14 | Wrapped containers: `.gz`, `.zip` (incl. a `.fit` inside a zip) | `container/gzip-wrapped`, `container/zip-wrapped` |
| 15 | Wrong format in disguise: GPX/TCX/HTML/JSON named `.fit` | `container/gpx-renamed`, `tcx-renamed`, `html-error-page`, `json-error` |
| 16 | Structurally fine but empty — honest non-recovery | `structural/empty-shell` |
| 18 | Content hash on canonical output, not raw bytes | every case (`source.sha256`) |
| 2, 3 | Truncation salvage with `recovered / estimated` | `structural/truncated-*` |
| 4, 5 | CRC triage: why it failed, not just that it did | `structural/bad-file-crc` |
| 103 | PII stripping: `user_profile`, serials | `strip_pii` unit tests |
| — | File-type routing by `file_id.type` | `routing/course-file`, `workout-file`, `monitoring-file` |

## Requirements

### 1. `js/src/inflate.ts` — the module Python does not need
1. Raw DEFLATE (RFC 1951), gzip (RFC 1952) and the ZIP local-file-header subset needed to read
   `.fit` entries — stored and deflated.
2. **Zero dependencies and synchronous**, so `parse()` behaves identically in Node, browsers, Deno
   and Bun (ADR-0009 §7). `node:zlib` is Node-only; `DecompressionStream` is async and would make
   `parse()` async in one runtime and not the other.
3. Malformed input returns a typed failure, never throws — the same contract the frame reader
   carries. A corrupt gzip header is a `NOT_FIT_FORMAT` defect, not an exception.
4. **Bounded output, as a deliberate divergence** *(amendment D4)*. A decompression bomb must fail
   with a defect rather than exhaust memory. Python is **not** bounded here — `gzip.decompress`
   reads until EOF and fails by `MemoryError` — so this is a place where the twins intentionally
   differ, and it must be recorded as such rather than presented as parity. The justification is
   the runtime: a malicious file that kills a Node process is bad, and one that kills a browser tab
   is worse. No corpus case exercises it, so the gate will not see the difference either way; the
   divergence is documented in the implementation doc and in ADR-0009's divergence list.
4a. **Inflate is the largest net-new module in the port and has no Python twin to check against**
   *(amendment D3)*. Everything else is a transliteration whose reference implementation can be
   diffed line by line; this is ~250 lines of original code, and the corpus exercises it through
   exactly **two** cases (`container/gzip-wrapped`, `container/zip-wrapped`). DEFLATE has three
   block types — stored, fixed-Huffman, dynamic-Huffman — and an implementation that handles two
   correctly would pass both corpus cases. Vectors are therefore required to cover, generated from
   Python's `zlib`/`gzip`:
   - all three block types explicitly (incompressible, tiny, and highly repetitive inputs),
   - inputs crossing the 32 KiB window boundary, so back-references reach past it,
   - every compression level 0–9,
   - truncated and corrupt streams, which must produce a defect rather than a throw.
   This is the F34 lesson applied before the fact: a gate that passes is not the same as coverage.

### 2. `js/src/intake.ts`
5. `unwrap(data)` mirroring `intake.py`: peel up to `MAX_UNWRAP_DEPTH` (3) containers, then sniff.
6. Sniffing identifies GPX, TCX, HTML, JSON and CSV by content, producing `NOT_FIT_FORMAT` with the
   detected name — contract #5's "route to the parser the error names".
7. Unrecognized bytes fall through to the frame reader, whose defects are more precise than a guess.

### 3. `js/src/api.ts` — `parse()`
8. `parse(src, { mode, stripPii, includeUnknown, includeRaw })` mirroring `_api.parse`.
9. The chained-part loop, `_buildPart` routing by `file_id.type`, and per-part message assembly.
10. Mode policy: `strict` raises the first defect; `lenient` recovers and collects; `forensic`
    detects like lenient but never drops values. `_CONTINUE_CODES` governs which defects are
    survivable.
11. `RecoveryReport`: recovered records, estimated total (`null` when honestly unknowable),
    bytes read, bytes skipped, resync count.
11a. **`estimatedTotalRecords` uses `pyRound`, not `Math.round`** *(amendment D2)*.
    `_api.py:255` computes it as `round(len(messages) * header.data_size / body_bytes_decoded)` —
    Python's single-argument `round`, which is half-to-even. This is `numeric.ts`'s **first real
    caller in the entire port**, and the value lands in canonical output. The `Math.round` guard
    turns a mistake here into a lint failure rather than a wrong number, which is the guard working
    as intended — but the requirement is stated so the implementer reaches for the right function
    instead of fighting the linter.
12. `stripPii` removes `user_profile` messages and `serial_number` fields, emitting provenance —
    never silently (contract #1, #10).
13. `includeUnknown: false` drops `unknown_*` messages, emitting provenance.
14. **Input is `Uint8Array` or a path.** A path is read through `node:fs`, imported **lazily** so
    the module still loads in a browser (the pack smoke asserts no `node:` import at module load).

### 4. `js/src/result.ts` — canonical shaping
15. `ParseResult` with `ok`, `mode`, `source`, `parts`, `provenance`, `warnings`, `errors`,
    `recovery`, and the delegating conveniences (`fileType`, `messages`, `activity`).
16. `toJSON()` and `toCanonicalJson()` producing `chiptime_schema: 1` — the shape PRD §7.5 fixes.
17. The ADR-0002 number policy at the shaping boundary: bytes to hex, magnitudes beyond 2^53−1 to
    decimal strings. This is where F34's `bigint` raws become strings, and the only place they may.
18. `source.sha256` — SHA-256 over the input bytes. Node has `node:crypto`; browsers have
    `crypto.subtle`, which is **async**. A synchronous, zero-dependency SHA-256 is ~80 lines and
    keeps `parse()` synchronous everywhere; that is the same trade `inflate.ts` makes and it should
    be made the same way.

### 5. The gate
19. `scripts/check_parse_parity.py` compares canonical output between implementations across all 72
    cases, in two tiers:
    - **11 cases whose output has no `activity` block** (non-activity file types, rejects, empties):
      compared against the **committed `expected.json`**, byte for byte. This is the real thing —
      TypeScript producing the corpus snapshot, including their provenance, warnings and errors,
      which at these cases originate entirely in intake and decode.
    - **61 activity cases**: compared on a **whitelist of the top-level keys F35 owns** —
      `chiptime_schema`, `ok`, `mode`, `source`, `recovery`, `errors`, and per part `file_type`,
      `file_id` and `messages` *(amendment D1)*.

    **Not** "everything except `activity`", which is what this spec originally said and which does
    not work: 52 of the 61 activity cases carry provenance or warnings whose dominant codes come
    from the semantic layer — `SESSION_REBUILT` (28 cases), `ACTIVITY_MESSAGE_MISSING` (9),
    `MOVEMENT_WITHOUT_DISTANCE` (7), `TIMER_STOP_SYNTHESIZED`, `HR_FLATLINE`, `ENHANCED_PAIR_*`.
    Eliding one key would have failed 52 cases for reasons entirely outside this feature. Those
    streams are gated at F36, where the code that produces them exists.
20. Modes: all three compared, not just lenient.
21. The truncation sweep extends to `parse()`: no throw, no hang, in every mode.

## Acceptance Criteria
- [ ] The 11 no-activity cases match their committed `expected.json` **byte for byte**
- [ ] All 72 cases match with `activity` elided, in all three modes
- [ ] `inflate.ts` matches Python's `zlib`/`gzip` over vectors spanning all three DEFLATE block
      types, window-crossing back-references, compression levels 0–9, and corrupt/truncated streams
- [ ] The output bound is documented as a deliberate divergence, not claimed as parity
- [ ] SHA-256 matches `hashlib.sha256` over the corpus inputs and a byte-sweep vector set
- [ ] `strip_pii` and `includeUnknown: false` emit provenance for everything they remove
- [ ] 64-bit raws serialize as decimal strings; nothing else changes shape
- [ ] No `node:` import executes at module load (pack smoke)
- [ ] Truncation sweep through `parse()`: no throw, no hang, all three modes
- [ ] Per-mode behavior explicitly compared, not assumed
- [ ] `estimatedTotalRecords` computed with `pyRound`
- [ ] `source` carries no local path (ADR-0002 §3: the path is excluded from canonical
      output for determinism and privacy)

## Public API Impact

**New TypeScript exports**: `parse`, `ParseResult`, `SourceInfo`, `RecoveryReport`, `FitPart` at the
root (mirroring `chiptime.__all__`); `unwrap` at `chiptime/intake`; the inflate helpers at
`chiptime/inflate`. Nothing published — npm publishing begins with the CLI feature.

No Python change. No canonical JSON schema change — this *implements* schema 1, it does not extend
it.

## Architectural Placement

**intake / api / output.** `intake.ts` is a leaf over `errors` and `inflate`. `api.ts` gains
`parse()` and sits above intake, frames, decode and (at F36) semantics. `result.ts` imports
`canonical`, `errors`, `message` — exactly as Python's does.

## Proposed Approach

Gate-first, as at F33 and F34. The two-tier gate (Requirement 19) exists because waiting for
semantics to compare anything would leave ~1,100 lines unverified; eliding one key buys a real
comparison now.

**The CLI is deliberately not in this feature.** `cli.py` is 580 lines with its own gate — stdout
bytes and exit codes — and depends on the semantic model for `parse --summary`. Bundling it here
would make F35 ~1,700 lines, larger than the F33 spec that was split for being unreviewable, and
would gate it on a model that does not exist yet. Proposed sequence:

| | |
|---|---|
| **F35** | intake, inflate, recovery, `parse()`, result shaping (~1,100 lines) |
| **F36** | semantics → all 72 canonical outputs byte-identical |
| **F37** | CLI (`parse`/`inspect`/`codes`), exit codes → **npm `0.1.0`** |

npm `0.1.0` lands at F37 rather than F36 because PyPI `0.1.0` shipped the CLI, and the version
mirrors a *surface*. Downstream features shift by one.

## Critique & Assessment

_Assessed 2026-08-21. Two of the spec's claims were measured against the corpus before assessing.
One was wrong in a way that would have made the feature's own gate unusable._

### Necessity and placement — fine
`parse()` is the product's one call; nothing above it exists without this. Layering matches Python:
`intake` is a leaf over `errors` and `inflate`, `api` sits above intake/frames/decode, `result`
imports `canonical`/`errors`/`message`. No cycles.

### The split — **approved**, with the sequence it implies

Removing the CLI leaves ~1,100 lines, between F33 (820) and the 1,600 that was split for being
unreviewable. The CLI is genuinely separable: 580 lines with its own gate (stdout bytes and exit
codes) and a hard dependency on the semantic model for `parse --summary`. Bundling it here would
both oversize this feature and gate it on a model that does not exist.

    F35  intake, inflate, recovery, parse(), result shaping
    F36  semantics -> all 72 canonical outputs byte-identical
    F37  CLI, exit codes -> npm 0.1.0

npm `0.1.0` moves to F37 because PyPI `0.1.0` shipped the CLI and the version mirrors a *surface*,
not a line count. Downstream shifts by one — the third renumber, and still a table edit.

### Finding 1 — the tier-2 gate could not have worked. **Measured.**

The spec proposed comparing all 72 cases with the `activity` key elided, on the reasoning that
everything else belongs to F35. It does not. Measured across the corpus:

- **52 of 61** activity cases carry provenance or warnings.
- The dominant codes are **semantic**: `SESSION_REBUILT` (28), `ACTIVITY_MESSAGE_MISSING` (9),
  `MOVEMENT_WITHOUT_DISTANCE` (7), plus `TIMER_STOP_SYNTHESIZED`, `HR_FLATLINE`,
  `ENHANCED_PAIR_MERGED`, `ENHANCED_PAIR_DISAGREES`, `DISTANCE_DECREASES`.

All of those originate in `semantics/`, which is F36. Eliding one key would have failed 52 of 61
cases for reasons entirely outside this feature — and the likely response to a gate failing that
broadly is to weaken it, which is how a gate stops meaning anything.

Fixed by amendment D1: tier two compares an explicit **whitelist of the keys F35 owns**. Tier one
is unchanged and is the valuable half — 11 cases matched byte for byte against their committed
`expected.json`, provenance and warnings included, because at those cases every entry originates in
intake or decode.

### Finding 2 — `numeric.ts` finally has a caller, and the spec did not say so

`estimatedTotalRecords` is `round(len(messages) * data_size / body_bytes_decoded)` at
`_api.py:255` — Python's half-to-even `round`, landing in canonical output. This is the **first
real caller of the number kernel built at F31**, four features ago, and the spec described the
field without mentioning it.

The `Math.round` guard means a mistake here fails lint rather than producing a wrong number, so the
system already protects itself — but a requirement that names `pyRound` is the difference between
an implementer reaching for the right function and an implementer fighting the linter. Amendment D2.

### Finding 3 — inflate has no twin, and two corpus cases will not cover it

Every other module in this port is a transliteration with a reference implementation that can be
diffed line by line. `inflate.ts` is ~250 lines of **original code**, and the corpus reaches it
through exactly two cases. DEFLATE has three block types; an implementation that gets stored and
fixed-Huffman right and dynamic-Huffman wrong would pass both of them.

This is F34's lesson applied *before* the fact rather than discovered by mutation afterwards, so
amendment D3 specifies the vector coverage up front: all three block types, back-references
crossing the 32 KiB window, compression levels 0–9, and corrupt/truncated streams that must defect
rather than throw.

### Finding 4 — the bomb bound is a divergence, and the spec called it parity

Requirement 4 said "Python inherits this bound from its stdlib". It does not: `gzip.decompress`
reads to EOF and fails by `MemoryError`. A bounded TypeScript implementation therefore **rejects
input Python accepts**.

Bounding is still right — a malicious file that kills a Node process is bad and one that kills a
browser tab is worse — but it is a deliberate divergence and must be recorded as one. No corpus
case exercises it, so the gate is silent either way, which is exactly when a divergence needs
writing down rather than assuming. Amendment D4, and it belongs in ADR-0009's divergence list
alongside the integral-float asymmetry.

### Hand-rolling: justified, and worth stating why once
Three constraints intersect — zero runtime dependencies, synchronous `parse()`, and browser
support. `node:zlib` fails the third, `DecompressionStream` the second, a dependency the first.
Same for SHA-256: `node:crypto` is Node-only and `crypto.subtle` is async. Neither is a preference;
both are forced, and both are small and vector-testable. **Alternatives considered:** (1) accept an
async `parse()` in the browser — rejected, it forks the API the whole port exists to keep identical;
(2) take a dependency on `fflate` — rejected, ADR-0009 §7, and it would be the first runtime
dependency in either language; (3) ship two builds with different backends — rejected, it doubles
the surface the parity gates have to cover for no user-visible gain.

### At scale
`inflate` and SHA-256 both run over whole files; an ultra-length activity is tens of megabytes.
Neither is quadratic, and F35 sets no performance gate — but the bomb bound (D4) is the one place
where hostile input meets unbounded allocation, and it is now explicit.

### Contract check
- **Silent loss** — `stripPii` and `includeUnknown: false` both emit provenance (Requirements 12,
  13). These are the only paths in this feature that remove data, and both are gated by tier one,
  since PII stripping is exercised by unit tests and unknown-dropping changes `parts[].messages`.
- **Determinism** — `source` must carry no local path (ADR-0002 §3, now an acceptance criterion);
  no wall clock; `pyRound` for the one rounded value.
- **Sentinels & zero-vs-null** — inherited from F34, unchanged here.
- **Modes** — all three are compared by the gate, not just lenient (Requirement 20). This is the
  first feature where the three genuinely differ, so that matters more than it did.
- **Errors** — `NOT_FIT_FORMAT` carries the detected format name; suggestions come from the table
  ported at F33.
- **Corpus** — no new cases; every claimed taxonomy item maps to an existing one.

### Blast radius
Total, and mostly loud: `parse()` is the entry point, so a defect fails tier one immediately. The
quiet corner is `inflate` — two corpus cases, one code path each — which is precisely what
amendment D3 addresses.

### Simplification — nothing cut
The 20% version would be "skip inflate, support only bare `.fit` bytes". That drops taxonomy #14
and two corpus cases, and container-wrapped files are among the most common real-world inputs
(Garmin Connect exports are zips). Not a simplification, a scope cut with a user-visible hole.

### Final decision: **APPROVE** — with amendments D1–D4 and the F35/F36/F37 sequence

The feature is right; its gate was not, and its riskiest module was under-specified. Both are fixed
in the requirements. Tier one of the corrected gate is the milestone worth naming: **the first
TypeScript output compared byte for byte against a committed corpus snapshot.**

## Dependencies
- **Depends on:** F31 (canonical), F32 (profile), F33 (frames/errors), F34 (decoder);
  F4/F5/F11/F15 in Python as the reference; ADR-0002, ADR-0003, ADR-0009
- **Depended on by:** F36 (semantics fills the `activity` block), F37+ (everything else)

## Related
- ADR: [0002](../architecture/adrs/0002-canonical-json.md), [0003](../architecture/adrs/0003-defects-as-values-and-modes.md), [0009](../architecture/adrs/0009-cross-language-parity.md)
- Plan: [../m3-typescript-plan.md](../m3-typescript-plan.md)
- Implementation: `../implementation/f35-js-intake-parse.md` (created by `/implement`)
