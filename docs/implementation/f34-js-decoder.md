# Implementation: F34 — The decoder for TypeScript

> Feature Spec: [../features/f34-js-decoder.md](../features/f34-js-decoder.md)
> Plan: [../m3-typescript-plan.md](../m3-typescript-plan.md) · Contract: [ADR-0009](../architecture/adrs/0009-cross-language-parity.md)

## Summary

TypeScript reads FIT *values*. `Decoder` produces the same 3,213 messages, 14 diagnostics and 6
provenance entries as Python across all 72 corpus cases, byte-identically — sentinels resolved,
scales applied, enums named, strings segmented, timestamps formatted, developer fields promoted,
components expanded.

It passed all 72 on the first gate run. That is a claim worth distrusting, so the gate was
mutation-tested; what that exposed is the most useful finding of the feature.

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `js/src/decode.ts` | Added | `Decoder`, `civilFromUnix`, `fitTsToIso`/`Local`, `sanitizeFieldName` |
| `js/src/api.ts` | Modified | `iterMessages` |
| `js/src/index.ts` | Modified | Root gains `iterMessages` |
| `js/package.json` | Modified | `chiptime/decode` subpath export |
| `js/test/decode.test.ts` | Added | 53 tests, including the two paths the corpus cannot reach |
| `js/test/vectors/utf8.json`, `timestamps.json` | Added | 19 UTF-8 + 15 timestamp vectors from CPython |
| `js/scripts/guards.mjs` | Modified | `Date` ban (amendment C4) |
| `scripts/check_message_parity.py` | Added | The 72-case message gate |
| `scripts/gen_parity_vectors.py` | Modified | Emits `utf8.json`, `timestamps.json` |
| `.github/workflows/ci.yml`, `.githooks/pre-push` | Modified | Message parity gate |

## Corpus Cases Added

None — as at F33, the fixtures already existed. But see Lessons: this feature is the first where
the corpus was shown to have **blind spots**, and the response was targeted unit tests rather than
new corpus cases, because the uncovered behaviors are decoder-internal rather than file-shaped.

## Key Implementation Decisions

1. **Modulo arithmetic instead of bitwise masking, everywhere a timestamp is involved.** JavaScript's
   `&`, `|` and `~` coerce to **32-bit signed**. FIT `date_time` is a `uint32` whose values reach
   4.29e9, so Python's `anchor & ~0x1F` becomes a negative number in TypeScript. Every masking site
   in the timestamp paths (`compressedTimestamp`, `mergeTimestamp16`, `expandHr`) uses subtraction
   and `%` instead. This was found by reading, not by the gate — the corpus's timestamps are all
   below 2^31, so the bug would have shipped and surfaced in 2038.

2. **`floorMod` for the rollover math.** Python's `%` takes the divisor's sign; JavaScript's takes
   the dividend's. `(dist12 - last) % 4096` is a rollover computation that depends on the Python
   behavior.

3. **`toNumber()` at each `bigint` boundary, named and commented.** Mixed `bigint`/`number`
   arithmetic throws, so every scale/offset site converts explicitly. The conversion is lossy beyond
   2^53 — which is exactly why the shaping layer stringifies such values (ADR-0002 §2) — and the
   *raw* is preserved on the `FieldValue` regardless, so nothing the output needs is lost.

4. **The salvage aggregation keeps its tuple.** Python sorts by `(defOffset, fieldNum, why)`. A
   `Map` needs a string key, and string keys sort lexicographically — `"100 …"` before `"20 …"`.
   The map value carries the tuple components so `finish()` can sort numerically.

5. **`TextDecoder` via a minimal ambient declaration**, not the DOM lib, which would let genuinely
   browser-only APIs compile by accident.

## Deviations from Spec

None. Amendments C1–C5 were implemented as written: provenance with both ordering rules (C1), the
gate driving `Decoder` directly (C2), the synthetic `uint64`-with-scale test (C3), the `Date` guard
(C4), and `includeRaw` confirmed as no work at this layer (C5).

## Lessons Learned

- **A first-run pass deserves an attack, and the attack found the real problem.** All 72 cases
  matched immediately. Rather than accept that, the gate was mutation-tested — and two mutations
  **passed**:

  | Mutation | Corpus verdict | Why |
  |---|---|---|
  | Sentinel check moved *after* the enum branch | ✅ passed | No corpus case carries a sentinel on an enum field |
  | Salvage provenance sorted lexicographically | ✅ passed | Only 6 provenance entries exist; no two ever disagree between the orderings |

  Three further mutations (removing sentinel handling, a one-second epoch shift, dropping `units`)
  were caught immediately, across 1, 59 and 52 cases. So the gate has teeth — but it has **holes**,
  and the holes sat exactly where the critique had predicted the danger (amendment C1's ordering
  rule, and contract #4's sentinel-before-scale).

  The critique identified both hazards. The port handled both correctly. **Nothing would have
  caught getting them wrong.** Targeted unit tests now cover both, and each was verified to fail
  under its corresponding mutation.

- **"All green" and "adequately tested" are different claims.** The corpus is a strong gate for
  file-shaped behavior and a weak one for decoder-internal ordering, because a fixture can only
  exercise what a real file contains. Mutation testing is how you tell the difference, and it cost
  about ten minutes.

- **The bugs a corpus cannot catch are found by reading the *language*, not the code.** The 32-bit
  bitwise hazard is invisible to every test we have — all corpus timestamps are under 2^31 — and
  invisible to a reviewer comparing the two sources line by line, because `anchor & ~0x1F` is a
  *correct transliteration*. It is only visible if you know what `&` does in JavaScript.

- **Vectors must be generated from the path under test.** The first UTF-8 vector set recorded
  `bytes.decode("utf-8", errors="replace")`, and one case failed — correctly, because the decoder's
  string path segments on NUL and discards padding junk, so `a\\x00b` yields `"a"`, not `"a\\x00b"`.
  The vector was testing `TextDecoder` in isolation while claiming to test the decoder. Regenerated
  from `Decoder._string`.

## Post-Implementation Checklist
- [x] Feature spec status updated to DONE
- [x] INDEX.md updated
- [x] DEPENDENCY_MAP.md updated
- [x] Architecture docs updated (OVERVIEW decode row)
- [x] All new behavior covered by unit tests (404 total) and the 72-case message gate
- [x] Every new drop/repair/reinterpretation emits provenance — salvage aggregation and the
      compressed-timestamp anchor, both gated, both with their ordering verified by unit test
- [x] Determinism verified (message gate byte-identical; cross-process hash unchanged)
- [ ] Skills assessed and updated (`/post-impl-review`)
