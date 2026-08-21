# Implementation: F35 — Intake, inflate, recovery and `parse()` for TypeScript

> Feature Spec: [../features/f35-js-intake-parse.md](../features/f35-js-intake-parse.md)
> Plan: [../m3-typescript-plan.md](../m3-typescript-plan.md) · Contract: [ADR-0009](../architecture/adrs/0009-cross-language-parity.md)

## Summary

TypeScript has `parse()`. **11 corpus cases now come out byte-identical to their committed
`expected.json`** — the first TypeScript output measured against a corpus snapshot rather than a
generated vector — and all 216 case/mode combinations agree with Python on the keys F35 owns.

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `js/src/inflate.ts` | Added | DEFLATE/gzip/zlib/zip, CRC-32 + Adler-32 trailers, bounded output |
| `js/src/sha256.ts` | Added | Synchronous SHA-256 |
| `js/src/intake.ts` | Added | Container unwrapping, content sniffing |
| `js/src/result.ts` | Added | `ParseResult`, `chiptime_schema: 1` shaping |
| `js/src/api.ts` | Modified | `parse()`: modes, chained parts, PII, recovery report |
| `js/src/index.ts`, `js/package.json` | Modified | `parse` at the root; five new subpath exports |
| `js/test/inflate.test.ts`, `parse.test.ts` | Added | 211 + 19 tests |
| `js/test/vectors/inflate*.json`, `sha256.json` | Added | 90 inflate + 7 corrupt + 18 SHA-256 vectors |
| `scripts/check_parse_parity.py` | Added | The two-tier gate |
| `scripts/gen_parity_vectors.py` | Modified | Inflate/SHA-256 vectors |
| `.github/workflows/ci.yml`, `.githooks/pre-push` | Modified | `parse()` parity gate |

## Corpus Cases Added

None. Fourth feature running — and this is the one where that promise pays its largest dividend:
11 committed snapshots, written by Python months ago, reproduced byte for byte by an
implementation in another language with no new fixtures written.

## Key Implementation Decisions

1. **`sha256Hex(raw)` hashes the *original* bytes, before unwrapping.** Hashing post-unwrap would
   make a `.gz` and its contents indistinguishable, breaking the dedup identity of taxonomy #18.
   Covered by a test that asserts the two differ.

2. **`readZipEntries` walks local file headers rather than the central directory.** The directory
   is the canonical index, but a truncated archive often keeps readable local headers after it is
   gone — and salvaging what is there is this library's whole posture. Entries that fail to inflate
   are skipped rather than aborting the archive.

3. **`parse()` takes `Uint8Array` only.** Path input moves to the CLI (F37), which is where a
   filesystem exists. Keeping `node:fs` out of this module is what lets the package load in a
   browser, and the pack smoke asserts it.

4. **`estimatedTotalRecords` uses `pyRound`** (amendment D2) — `numeric.ts`'s first caller in the
   port, four features after it was built.

## Deviations from Spec

1. **Tier 2 of the gate had to shed one more key than the critique found.** Amendment D1 removed
   provenance and warnings from the activity-case comparison. Implementation showed
   `parts[].messages` has to go too: Python **drops record messages from the message list when an
   activity model is present** (they live in streams instead), and TypeScript has no model yet, so
   the lists legitimately differ until F36. The tier-2 whitelist is therefore
   `chiptime_schema, ok, mode, source, recovery, errors` plus per-part `file_type` and `file_id`.

   Tier 1 is unaffected and is where the real claim lives.

2. **`gunzip` needed trailer validation the spec did not mention.** Covered in the inflate commit:
   Python's `gzip.decompress` checks CRC-32 and ISIZE, so skipping them would have accepted
   corrupt bodies Python rejects.

## Lessons Learned

- **The vector-freshness gate caught a wall-clock dependency in the vector generator itself.**
  `gzip.compress()` stamps MTIME into the header, so regenerating the corrupt-stream vectors
  produced different bytes on every run. The gate built at F31 to catch *Python behavior changes*
  caught *me* violating the determinism rule the whole project rests on. Fixed with `mtime=0`, and
  verified by generating twice and comparing hashes.

  The general shape is worth keeping: a determinism gate does not only protect the contract from
  the code, it protects the contract from the tooling that describes it.

- **Mutation testing is now cheap enough to be routine.** Three mutations on the new gate — dropping
  a provenance entry, hashing the wrong bytes, omitting `units` — were caught at 2, 6 and 5 cases
  respectively, with the divergence localized to a character offset. Two minutes, and the
  difference between "the gate passed" and "the gate works".

- **A gate's scope is a design decision that deserves measurement, not intuition.** The critique
  found the tier-2 problem by counting semantic provenance codes across the corpus; implementation
  found the remaining one by reading `_part_dict`. Both were invisible from the spec.

## Post-Implementation Checklist
- [x] Feature spec status updated to DONE
- [x] INDEX.md updated
- [x] DEPENDENCY_MAP.md updated
- [x] Architecture docs updated
- [x] All new behavior covered by unit tests (634 total) and the two-tier parity gate
- [x] Every new drop/repair/reinterpretation emits provenance — `PII_STRIPPED`,
      `UNKNOWN_MESSAGES_OMITTED`, `RESYNC_SKIPPED_BYTES`, `PREAMBLE_GARBAGE_SKIPPED`,
      `TRUNCATED_TAIL_SALVAGED`, `ZIP_ENTRIES_CHAINED`, all gated
- [x] Determinism verified (repeated parses byte-identical; vector generator made deterministic)
- [ ] Skills assessed and updated (`/post-impl-review`)
