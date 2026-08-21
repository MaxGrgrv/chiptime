# Feature: F34 — The decoder for TypeScript: frames to messages

> Status: CRITIQUED

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
6. `finish()` returns `DecodeOutput`: messages, diagnostics, **provenance**, and defects.
6a. **Provenance is not optional here — this module produces it** *(amendment C1)*. The decoder
   emits provenance at every salvage site (a field it could not decode and dropped) and when it
   anchors a compressed timestamp from `file_id.time_created` (taxonomy #21). Contract #1 says
   every drop and reinterpretation lands in `provenance[]`; the decoder is where several of those
   originate, and the original spec did not mention provenance at all.
6b. **The two orderings are different rules and both are observable** *(amendment C1)*:
   - **diagnostics** accumulate in the order they were produced;
   - **salvage provenance** is aggregated per `(definition offset, field number, reason)` and
     emitted from `finish()` **sorted by that key**, not in production order.
   Porting one rule to both sites would produce plausible output that fails the byte comparison.

### 2. Numbers — where the twins genuinely differ
7. **64-bit raws are `bigint`, and `bigint` does not mix with `number` arithmetic.** Python's
   `raw / fdef.scale` works for any int; TypeScript throws `TypeError: Cannot mix BigInt and other
   types`. Every arithmetic site that can receive a 64-bit raw must convert explicitly, and the
   conversion must be *documented at the site* with what it costs: beyond 2^53 the `number` result
   is lossy, which is exactly why the shaping layer stringifies those (ADR-0002 §2).

   **The exposure is wider than the corpus shows** *(amendment C3)*. Base types are declared per
   *definition frame*, not per profile field, so any of the **419 fields carrying a scale or
   offset** could arrive as a 64-bit raw from a file that declares it that way. The corpus
   exercises one such case; a real encoder could produce others. A grep audit is therefore not
   sufficient — this needs a **synthetic definition frame declaring a scaled field as `uint64`**,
   decoded in a unit test, so the crash surfaces here rather than in a user's file.
8. Enum lookup uses `Number(raw)` where Python uses `int(raw)`; safe because enum keys are small,
   and asserted rather than assumed.
9. `scale`/`offset` arithmetic is plain IEEE double division and subtraction in both languages —
   no rounding helper is involved, and `numeric.ts` must not be reached for. Where a value is
   rounded before output, that happens in the shaping layer (F35), not here.
9a. **`includeRaw` needs nothing here** *(amendment C5, closing F33's deferral)*. `FieldValue.raw`
   is populated unconditionally at decode time in Python; the flag only controls whether the
   shaping layer *emits* it. F33 deferred the question to "F34 and F35"; the F34 half of the answer
   is that there is no work, and recording that is cheaper than rediscovering it.

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
13a. **The `Date` ban becomes a source guard, not just a review note** *(amendment C4)*. It was
    logged to BACKLOG at F31 with F33 as the revisit trigger; F33 introduced no timestamps, so it
    lands here with the code it protects. Implemented in `js/scripts/guards.mjs` beside the
    `Math.round` ban, as a blanket grep over `js/src` with a per-file exemption list — the same
    shape, because a path-sensitive rule is not greppable. ADR-0009 §5 permits `Date` in public API
    return types as a convenience; nothing wants that yet, and when something does it takes an
    exemption entry and a sentence saying why.
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
22. **The harness drives `Decoder` directly, not `iterMessages`** *(amendment C2)*. `iter_messages`
    yields messages and never calls `finish()`, so diagnostics and provenance are unreachable
    through it — a gate written against `iterMessages` would silently compare nothing on the very
    outputs contract #1 governs. Both sides construct a decoder, feed it the data frames, call
    `finish()`, and compare messages, diagnostics **and** provenance, each under its own ordering
    rule (Requirement 6b). These become observable to users at F35 via `parse()`; gating them now
    is what stops a wrong ordering from being discovered a feature later.
23. The truncation sweep from F33 extends to `iterMessages`: no throw, no hang.

## Acceptance Criteria
- [ ] Message-level parity on **all 72** corpus cases (3,213 messages), byte-identical dumps
- [ ] Diagnostics identical in content and production order; salvage provenance identical and
      sorted by its own key — the two orderings verified separately
- [ ] 64-bit fields reach `FieldValue` as `bigint` with no precision loss, and every mixed-type
      arithmetic site is explicit
- [ ] Sentinels resolve to `null` **before** scaling; a real `0` survives as `0` (contract #4)
- [ ] Unknown enums, unknown messages and unknown fields decode rather than throw (contract #6)
- [ ] UTF-8 replacement matches CPython across the committed adversarial vectors
- [ ] `js/scripts/guards.mjs` bans `Date` in `js/src`, verified to exit non-zero on a probe file
- [ ] A synthetic `uint64`-declared scaled field decodes without a mixed-arithmetic throw
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

_Assessed 2026-08-21. Three of the spec's assumptions were checked against the Python source and
the profile tables before assessing. One held; two did not, and one of those was an omission rather
than an error._

### Necessity and placement — both fine
Without the decoder there are no values, no semantics and no `parse()`. `decode` imports `frames`,
`message`, `profile`, `errors`, `numeric` and never `semantics` — which does not exist yet, making
the rule easy to keep and worth stating precisely because this is the feature where borrowing from
it would first be tempting.

### Size — **no split**, and this time there is evidence

F33 was split at ~1,600 lines. F34 is ~800, and the question is whether that is still too much for
one critique and one review. It is not, and the argument is empirical rather than aesthetic: F33 as
finally shipped was ~820 lines of Python-equivalent (errors 245 + message 51 + frames 524), landed
in one feature, and hit 70/72 on the first gate run. F34 at 807 lines is the same size as a
demonstrated-manageable feature.

There is also no honest split available. The tempting one — core element decoding first, then
developer fields and expansions — gates stage one on "corpus cases without dev fields or
expansions", which is the exact mistake F33's critique caught: a gate scoped by convenience that
excludes its own subject. One feature, one 72-case gate.

### Finding 1 — the spec never mentioned provenance. **Contract #1 omission.**

The requirements described messages and diagnostics and stopped there. But `decode.py` emits
provenance at five sites: every `_salvage` call (a field it could not decode and dropped) and the
compressed-timestamp anchor synthesized from `file_id.time_created` (taxonomy #21). Contract #1 —
"every drop, repair and reinterpretation lands in `provenance[]`" — has several of its origins in
this module, and a spec that does not name them invites a port that quietly omits them. A dropped
field with no provenance entry is precisely the silent loss the contract exists to prevent.

Worse, the two output streams follow **different ordering rules**, and the spec's single sentence
about ordering would have produced the wrong one at one of the sites:

- diagnostics accumulate in **production order**;
- salvage provenance is aggregated per `(definition offset, field number, reason)` and emitted from
  `finish()` **sorted by that key**.

Porting one rule to both places yields output that looks entirely reasonable and fails the byte
comparison. Fixed by amendments C1 (Requirements 6, 6a, 6b).

### Finding 2 — the gate as specified could not see what it claimed to check

Requirement 22 said `finish()`'s diagnostics would be compared, while Requirement 21 built the
harness on `iterMessages`. Those are incompatible: `iter_messages` yields messages and **never
calls `finish()`**, so diagnostics and provenance are unreachable through it. The gate would have
compared nothing on exactly the outputs contract #1 governs, and reported success.

Fixed by amendment C2: both sides construct a `Decoder` directly, feed it the data frames, call
`finish()`, and compare all three streams under their respective ordering rules. These become
user-visible at F35 through `parse()`; gating them now is what stops a wrong ordering from
surfacing a feature later, when the cause is further away.

### Finding 3 — the `bigint` exposure is broader than "one corpus case"

The spec called mixed `bigint`/`number` arithmetic the sharpest hazard and proposed a grep audit.
The hazard is real; the audit is not sufficient. Base types are declared **per definition frame**,
not per profile field, so any of the **419 profile fields carrying a scale or offset** could arrive
as a 64-bit raw from a file that declares it that way. The corpus exercises one. A grep finds sites
that *look* exposed; it cannot show that a site handles a `bigint` correctly at run time.

Amendment C3 adds a synthetic definition frame declaring a scaled field as `uint64`, decoded in a
unit test. The failure mode this guards is good — TypeScript throws rather than computing something
wrong — but a throw in a user's file rather than in our test suite is still a bug we shipped.

### Finding 4 — the `Date` ban was an acceptance criterion, not a requirement

It was logged to BACKLOG at F31 with F33 as the revisit trigger. F33 introduced no timestamps, so
it correctly did not land there — but F34 is the feature that introduces them, and a criterion with
no requirement behind it is a thing to check rather than a thing to build. Promoted by amendment C4
into `js/scripts/guards.mjs` beside the `Math.round` ban: a blanket grep with a per-file exemption
list, because ADR-0009 §5's actual rule ("never on an output path") is not greppable. Nothing wants
`Date` in a return type yet; when something does, it costs an exemption entry and a sentence.

### Finding 5 — F33's deferred `includeRaw` question had a one-line answer

F33 deferred it to "F34 and F35". The F34 half is: nothing to do. `FieldValue.raw` is populated
unconditionally at decode time in Python; the flag only governs whether the shaping layer emits it.
Recorded by amendment C5 rather than left for someone to rediscover.

### Approach — gate-first is right, and now it has a track record
The spec proposes porting far enough to produce messages, then working down the failure list from a
72-case byte comparison. That is what F33 did, and the two bugs it found were both in places review
had already passed over. A byte comparison localizes a defect better than reading 800 lines twice.

**Alternatives considered.**
1. *Port fully, then gate.* The reading-twice approach. F33's evidence is directly against it: the
   frame reader was correct on the first attempt and the wrapper was not, and no amount of
   re-reading the reader would have found that.
2. *Split core decoding from expansions.* Rejected above — no honest gate for the first half.
3. *Hand-roll the UTF-8 decoder instead of using `TextDecoder`.* Would remove the ambient
   declaration and guarantee replacement semantics by construction. Rejected: the ten-sequence check
   showed CPython and WHATWG already agree, including on the maximal-subpart cases where they could
   have diverged, so this would be ~80 lines of subtle code replacing a correct built-in. The
   vectors keep it honest.

**At scale.** The decoder runs per field on every record — an ultra-length activity is millions of
calls. Python's version caches field plans per definition (`_build_plan`) for exactly this reason
and the port keeps that. No performance gate at F34; F35 owns `parse()` and the perf pass has its
own precedent (F20).

### Contract check
- **Silent loss** — the finding of the assessment. Provenance is now a requirement, with both
  ordering rules stated (C1) and gated (C2).
- **Sentinels & zero-vs-null** — Requirement 3 pins `_element`'s ordering, and the spec is right
  that getting it backwards produces *believable* numbers: `65535 / 100` reads fine. That is why it
  is a byte-comparison matter and not a review matter.
- **Determinism** — no wall clock, no randomness; `Date` now banned by a guard rather than by
  intention (C4). The two ordering rules are the determinism risk and are covered.
- **Modes** — correctly inherited from `iterFrames`: `strict` raises the first defect. Recovery
  differences between `lenient` and `forensic` are F35's and are stated as out of scope.
- **Errors** — no new failure paths; defects and their codes come from F33.
- **Corpus** — no new cases, and the taxonomy table maps every claimed item to an existing one.

### Dependency analysis
No cycles. `decode` sits above `frames`/`profile`/`errors`/`numeric` and below everything else.
**Blast radius is total and loud**: a decoder defect fails the 72-case gate immediately. The quiet
failure mode is the `bigint` one — a site that never sees a 64-bit raw in the corpus and throws in
production — which is why C3 adds a synthetic case rather than trusting coverage.

### Simplification — nothing cut
The requirements are the module's actual behavior; there is no 20% version of a decoder that
produces 80% of the right values, because "the right values" is a byte comparison. The only
reduction available would be dropping expansions or developer fields, which would fail the gate.

### Final decision: **APPROVE** — with amendments C1–C5 applied above

Two of the three checked assumptions were wrong, and both would have shipped: a spec silent on
provenance, and a gate that could not observe the outputs it claimed to compare. Both are fixed in
the requirements rather than left as review notes.

## Dependencies
- **Depends on:** F31 (canonical, numeric), F32 (profile tables), F33 (frames, errors, message);
  F3/F6/F22 in Python as the reference; ADR-0002, ADR-0003, ADR-0009
- **Depended on by:** F35 (intake, recovery, `parse()`), F36–F43

## Related
- ADR: [0002](../architecture/adrs/0002-canonical-json.md), [0003](../architecture/adrs/0003-defects-as-values-and-modes.md), [0009](../architecture/adrs/0009-cross-language-parity.md)
- Plan: [../m3-typescript-plan.md](../m3-typescript-plan.md)
- Implementation: `../implementation/f34-js-decoder.md` (created by `/implement`)
