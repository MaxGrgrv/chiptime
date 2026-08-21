# Feature: F34 — The decoder for TypeScript: frames to messages

> Status: DRAFT

## Purpose

Turn wire frames into profile-applied messages: base types, endianness, sentinels resolved to
`null`, scale and offset, enums, strings, arrays, compressed timestamps, developer fields,
component expansion, subfields and accumulators.

F33 made TypeScript read bytes. This makes it read *values* — the layer where "65535 W" becomes
`null`, where altitude becomes metres, and where a Stryd field acquires a name. It ports
`decode.py` (~800 lines, 18 methods), the single densest module in the package.

The gate is `iterMessages` over all 72 corpus cases: **3,213 messages**, every field, byte-identical.

## Context Check
- [x] `docs/PRD.md` — §6.1 (decode owns base types, endianness, compressed-timestamp math,
      developer-field resolution, component expansion, scale/offset), contract #4 (sentinels → null
      *before* statistics; zero ≠ null), contract #6 (unknown ≠ invalid)
- [x] `docs/INDEX.md` — mirrors F3 (decode core), F6 (developer fields), F22 (ecosystem hardening)
- [x] `docs/architecture/OVERVIEW.md` — `decode` imports `frames`, `message`, `profile`, `errors`;
      never `semantics`
- [x] `docs/dependencies/DEPENDENCY_MAP.md` — F33 supplies frames/errors, F32 the profile tables
- [x] `docs/edge-case-taxonomy.md` — items below
- [x] No duplication: `parse()`, recovery policy and result shaping are F35; semantics F36

## Taxonomy Coverage

**No new corpus cases.** As at F33, every item already has one — this feature makes the TypeScript
side produce identical values for the fixtures we have.

| Taxonomy item # | Summary | Corpus case(s) |
|---|---|---|
| 21 | Compressed timestamps: rollover math, missing anchor | `protocol/compressed-timestamps` |
| 22a–d | Developer fields: missing/late description, reused index, null names, no `developer_data_id`, known vendors | all six `devfields/*` |
| 23 | Compressed speed/distance component expansion | `protocol/compressed-speed-distance` |
| 24 | Unknown enum values preserved as raw ints | `protocol/unknown-enum-values` |
| 25 | Accumulator rollover | `protocol/accumulator-rollover` |
| 26 | Sentinel invalid values → `null`, **before** scaling | `protocol/sentinel-values` |
| 27 | Scale/offset, semicircles → degrees | `clean/ride-smooth`, `protocol/big-endian` |
| 35 | Float NaN / Infinity nulled with a diagnostic | `protocol/float-nan-inf`, `protocol/float-sentinel-vs-nan` |
| 36, 37 | FIT epoch; device-relative timestamps below `0x10000000` | `temporal/*` |
| 43 | 64-bit fields | `protocol/uint64-fields` |
| 53 | String edges: unterminated, multi-segment arrays, invalid UTF-8, padding junk | `protocol/string-edges`, `protocol/multi-string-arrays` |
| 64 | Zero is a real value; only sentinels become `null` | `protocol/sentinel-values` |
| — | Array fields, invalid base types, big-endian definitions, event subfields, pedal balance, product resolution, `hr` `event_timestamp_12` expansion | remaining `protocol/*`, `sensors/*` |

## Requirements

### 1. `js/src/decode.ts` — the `Decoder`
1. `Decoder` class mirroring Python's: `decode(frame)` → `Message`, `finish()` → `DecodeOutput`
   (messages, diagnostics, provenance, defects).
2. Field plans built per definition and cached, mirroring `_build_plan`; the fast path reads
   through `DataView` with the base type's accessor and the definition's endianness.
3. Base-type element decoding: `_element`'s order is **load-bearing** and must port exactly —
   non-finite float check, then sentinel → `null` (**before** scaling, contract #4), then enum
   resolution, then `date_time` / `local_date_time`, then scale, then offset.
4. Unknown enum values return the raw integer, not `null` (taxonomy #24, contract #6).
5. Arrays: a field whose declared size exceeds one element decodes to a list; single elements stay
   scalar.
6. `finish()` emits the accumulated diagnostics **in the order they were produced**. Ordering is
   observable in canonical output, so it is part of the contract, not an implementation detail.

### 2. Numbers — where the twins genuinely differ
7. **64-bit raws are `bigint`, and `bigint` does not mix with `number` arithmetic.** Python's
   `raw / fdef.scale` works for any int; TypeScript throws `TypeError: Cannot mix BigInt and other
   types`. Every arithmetic site that can receive a 64-bit raw must convert explicitly, and the
   conversion must be *documented at the site* with what it costs: beyond 2^53 the `number` result
   is lossy, which is exactly why the shaping layer stringifies those (ADR-0002 §2). This is the
   sharpest hazard in the feature and the most likely source of a silent wrong value.
8. Enum lookup uses `Number(raw)` where Python uses `int(raw)`; safe because enum keys are small,
   and asserted rather than assumed.
9. `scale`/`offset` arithmetic is plain IEEE double division and subtraction in both languages —
   no rounding helper is involved, and `numeric.ts` must not be reached for. Where a value is
   rounded before output, that happens in the shaping layer (F35), not here.

### 3. Strings
10. UTF-8 decoding with replacement, matching `bytes.decode("utf-8", errors="replace")`. **Verified
    equivalent** to `TextDecoder("utf-8")` across ten adversarial sequences — overlong encodings,
    lone surrogates in UTF-8 form, truncated multi-byte starts, out-of-range planes — including the
    maximal-subpart cases where the two specifications could have disagreed about how many U+FFFD
    to emit. Pinned by vectors so a runtime change would fail rather than silently alter values.
11. `TextDecoder` is used rather than hand-rolled. It is universal (Node ≥ 11, browsers, Deno, Bun)
    but absent from `lib: ["ES2022"]`, so it is introduced by a **minimal ambient declaration**
    rather than by pulling in the whole DOM lib — which would let genuinely browser-only APIs
    compile by accident.
12. The segmentation rules port exactly: up-to-NUL-or-end; multiple terminated segments are a
    string array; an unterminated tail *after* terminated segments is padding junk and is never
    decoded; an empty segment ends the array; undecodable content after valid segments is padding.
    Each of the three diagnostics (`STRING_UNTERMINATED`, `STRING_DECODE_REPLACED`) fires under the
    same conditions.

### 4. Timestamps
13. `civilFromUnix` (Hinnant, integer-only) plus `fitTsToIso` and `fitTsToIsoLocal`. **`Date` never
    appears** (ADR-0009 §5); `floorDiv`/`divmod` from `numeric.ts` supply Python's floor semantics.
14. Values below `RELATIVE_TS_CEILING` (`0x10000000`) are device-relative: `null` plus a
    `RELATIVE_TIMESTAMP` diagnostic (taxonomy #36/#37).
15. Compressed-timestamp rollover against the running anchor, including multiple rollovers between
    records and the missing-anchor case.

### 5. Developer fields and expansions
16. Developer-field description resolution: late descriptions, reused indices, null names, missing
    `developer_data_id`, and vendor promotion through `profile/registry.ts`. `DevFieldOrigin` is
    populated on every developer `FieldValue`.
17. `_sanitize_field_name`'s `[^a-z0-9]+` collapsing. ASCII-only in practice, but Python's `re` and
    JavaScript's regex engine differ on Unicode classes, so the behavior is pinned by tests rather
    than assumed.
18. Component expansion: `record` components, `hr` `event_timestamp_12` (12-bit), compressed
    speed/distance; `timestamp16` merging; accumulator rollover; pedal balance; product resolution;
    event subfields.

### 6. Public surface
19. `iterMessages(src, { mode })` exported from the package root, mirroring `iter_messages`.
    Python defines it as `iter_frames` filtered to data frames through one `Decoder` — the port
    does the same rather than reimplementing the loop.
20. `Decoder` and the decode helpers are reachable at `chiptime/decode`, mirroring
    `chiptime.decode`. The root gains only `iterMessages` (ADR-0009 §2; the twin-surface check has
    fired on every feature that added surface, so the default is *not* to hoist).

### 7. The gate
21. `scripts/check_message_parity.py`, in the shape `check_frame_parity.py` established: both
    implementations run `iterMessages` over **all 72** corpus cases, each serializes with its own
    canonical JSON, and the byte strings must match. Message number, name, local id, byte offset,
    and every field's `value`, `raw`, `units` and developer origin.
22. `finish()`'s diagnostics are compared too, in order — a decoder that produces the right values
    while reporting different diagnostics is not at parity.
23. The truncation sweep from F33 extends to `iterMessages`: no throw, no hang.

## Acceptance Criteria
- [ ] Message-level parity on **all 72** corpus cases (3,213 messages), byte-identical dumps
- [ ] Diagnostics identical in content **and order**
- [ ] 64-bit fields reach `FieldValue` as `bigint` with no precision loss, and every mixed-type
      arithmetic site is explicit
- [ ] Sentinels resolve to `null` **before** scaling; a real `0` survives as `0` (contract #4)
- [ ] Unknown enums, unknown messages and unknown fields decode rather than throw (contract #6)
- [ ] UTF-8 replacement matches CPython across the committed adversarial vectors
- [ ] `Date` appears nowhere in `js/src`; enforced by a guard alongside the `Math.round` ban
- [ ] Truncation sweep: no throw, no hang, through the decoder
- [ ] `tsc`, Biome, guards, vitest, determinism, pack smoke, and all five parity gates green
- [ ] Per-mode behavior: `strict` raises the first defect (inherited from `iterFrames`);
      `lenient`/`forensic` collect. Recovery differences between them arrive at F35

## Public API Impact

**New TypeScript exports**: `iterMessages` at the root; `Decoder` and helpers at `chiptime/decode`.
Nothing published — npm publishing begins at F36.

No Python change. No canonical JSON schema change: `parse()` and its output shape are F35's.

New dev tooling: `scripts/check_message_parity.py`; UTF-8 vectors added to
`scripts/gen_parity_vectors.py`.

## Architectural Placement

**`decode` layer.** `decode.ts` imports `frames`, `message`, `profile`, `errors`, `numeric` — and
never `semantics`. Semantics does not exist yet; the rule is stated because this is the feature
where borrowing from it would first be tempting.

## Proposed Approach

The F33 pattern, which found two real bugs and cost nothing: build the gate first, run it, let it
tell you what is wrong. Concretely — port `decode.ts` far enough to produce messages at all, run
`check_message_parity.py` over the corpus, then work the failure list down. A 72-case byte
comparison localizes a defect better than reading 800 lines twice.

Two things get their own attention before the bulk port, because they are the places where a wrong
answer looks right:

- **The `bigint` boundary** (Requirement 7). Mixed arithmetic throws rather than silently
  misbehaving, which is good — but only the `uint64-fields` case exercises it, so a missing
  conversion elsewhere would surface as a crash in the field rather than a test failure here.
  Audited by grep, not just by gate.
- **`_element`'s ordering** (Requirement 3). Sentinel-before-scale is contract #4. Getting it
  backwards yields plausible numbers — `65535 / 100` is a believable value — so it would pass a
  smell test and fail the byte comparison. That is precisely what the corpus is for.

## Critique & Assessment
_To be filled in by `/critique`. Worth challenging: is this still too large after the F33 split
(18 methods, ~800 lines), and is "port then gate" the right order given F33's finding that the
gate caught what review would not have?_
- **Alternatives considered:** _..._
- **Risks identified:** _..._
- **Simplification opportunities:** _..._
- **Contract check (silent loss / determinism / provenance / sentinels):** _..._
- **Final decision:** _pending_

## Dependencies
- **Depends on:** F31 (canonical, numeric), F32 (profile tables), F33 (frames, errors, message);
  F3/F6/F22 in Python as the reference; ADR-0002, ADR-0003, ADR-0009
- **Depended on by:** F35 (intake, recovery, `parse()`), F36–F43

## Related
- ADR: [0002](../architecture/adrs/0002-canonical-json.md), [0003](../architecture/adrs/0003-defects-as-values-and-modes.md), [0009](../architecture/adrs/0009-cross-language-parity.md)
- Plan: [../m3-typescript-plan.md](../m3-typescript-plan.md)
- Implementation: `../implementation/f34-js-decoder.md` (created by `/implement`)
