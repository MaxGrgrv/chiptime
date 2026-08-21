# Implementation: F32 — Profile tables for TypeScript

> Feature Spec: [../features/f32-js-profile-tables.md](../features/f32-js-profile-tables.md)
> Plan: [../m3-typescript-plan.md](../m3-typescript-plan.md) · Contract: [ADR-0009 §8](../architecture/adrs/0009-cross-language-parity.md)

## Summary

The TypeScript decoder now has the data it will decode with: 17 base types, 119 merged messages
(1,382 fields), 176 enums (3,640 values), and the 8-row vendor developer-field registry.

`generated.ts` is transcoded from the Python package's *merged* tables rather than emitted from the
SDK, so the merge policy has one implementation and drift is impossible to commit. Two gates guard
it — regenerate-and-diff for staleness, and a value-level check through `node` for transcoding
faults.

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `docs/architecture/adrs/0009-cross-language-parity.md` | Modified | §8 rewritten before any code, per the critique's required follow-up |
| `js/src/profile/base-types.ts` | Added | 17 base types, `DataView` accessors, `bigint` sentinels, `isInvalid` |
| `js/src/profile/core.ts` | Added | `FieldDef` / `MessageDef` shapes, `SEMICIRCLE_SCALE` |
| `js/src/profile/generated.ts` | Added (generated) | 200 KB of merged tables; excluded from Biome — the generator owns its formatting |
| `js/src/profile/index.ts` | Added | Mirrors `profile/__init__.py`'s export surface |
| `js/src/profile/registry.ts` | Added | Vendor developer-field registry, hand-ported |
| `js/test/profile.test.ts` | Added | 133 tests: `isInvalid` vectors, table sanity, unknown tolerance, registry |
| `js/test/vectors.ts`, `js/test/vectors/base-types.json` | Modified/Added | 116 `isInvalid` vectors from CPython |
| `js/biome.json` | Modified | Ignores the generated table |
| `scripts/gen_profile_ts.py` | Added | The transcoder |
| `scripts/check_profile_parity.py` | Added | Value-level parity through `node` |
| `scripts/gen_parity_vectors.py` | Modified | Emits `base-types.json` |
| `.github/workflows/ci.yml` | Modified | `parity-vectors` job broadened to `parity`: vectors + profile staleness + profile values |
| `.githooks/pre-push` | Modified | Same three gates locally |

## Corpus Cases Added

None — data layer, as specified. The taxonomy items these tables serve (#26 sentinels, #27
scale/offset, #22d vendor fields) get their corpus cases at F33, the first feature that can produce
a snapshot. Contract #6 (unknown ≠ invalid) is the one behavior F32 owns outright and is covered by
unit tests here.

## Key Implementation Decisions

1. **`generated.ts` is excluded from Biome.** A generated file with a generator that controls its
   own formatting should not also be owned by a formatter — that is a fight with no winner. The
   generator emits deterministically; `tsc` still type-checks it.

2. **`S` is emitted as `2 ** 31 / 180.0`, not as its decimal expansion.** `core.py` writes the
   semicircle scale as an expression; emitting `11930464.711111112` would be numerically identical
   but would hide that these are the same constant (#27).

3. **The vendor registry key is a joined string, not a tuple.** Python keys on
   `(vendor, field_name)`; TypeScript has no tuple keys for object lookup. Joined with a space,
   which is unambiguous because vendor names are enum identifiers containing none. The tests cover
   `__proto__` and `constructor` as keys, since a plain object lookup would otherwise answer from
   the prototype chain.

4. **`index.ts` exports `MESSAGES`/`ENUMS` as aliases of the generated tables.** Python merges at
   import time; TypeScript consumes the merged result. The alias keeps the *name* Python exports so
   consumers read the same way, while the docstring says plainly where the merge happened.

## Deviations from Spec

1. **ADR-0009 §8 was rewritten, as the critique required** — the ADR described a dual emitter this
   feature deliberately does not build. It now specifies transcoding, merged-table emission, the
   two distinct gates, and — newly — names `check_profile_against_fitdecode.py` as the thing
   standing between us and a two-language shared bug, promoting it from an F18 artifact to part of
   the release path.

2. **Size measured, per amendment B3.** Numbers from the built artifact:

   | | raw | gzipped |
   |---|---|---|
   | `dist/esm/profile/generated.js` | 225 KB | 41 KB |
   | whole `dist/esm` | 262 KB | 73 KB |
   | `npm pack` tarball (incl. maps + types) | 129 KB | — |

   Importing `profile/index.js` costs **6.3 ms**, nearly all of it parsing the table literal. Both
   numbers are acceptable for a parsing library and neither should be a surprise later: a complete
   profile is the product, and no consumer can tree-shake past it.

### Fixed during `/verify`

3. **`index.ts` re-exported the vendor registry; Python does not.** `lookup` and `VendorField`
   were surfaced from `js/src/profile/index.ts`, but Python reaches them as
   `chiptime.profile.registry.lookup` — so the TypeScript surface carried a name at an address the
   twin does not have. Removed, with the reason stated in the file. Caught by the twin-surface
   check `/verify` gained in F31, on its first use against a non-trivial module.

   Worth noting for future runs of that check: type-only exports (`BaseType`, `FieldDef`,
   `MessageDef`) erase at runtime and never appear in `Object.keys`, so the comparison needs
   reading rather than diffing — Python exporting three names TypeScript "lacks" was correct here.

## Lessons Learned

- **The differential vectors found a crash, not a mismatch.** `isInvalid` used
  `BigInt(value) === BigInt(sentinel)` to compare a mixed number/bigint pair. `BigInt(NaN)` throws
  a `RangeError` — so a corrupt float read reaching a 64-bit type would have **crashed the
  decoder**, in a layer whose whole design promise is being incapable of crashing on hostile input.
  Python returns `False` there without comment, because `nan == 0xFFFFFFFFFFFFFFFF` is simply
  false.

  The vector that caught it exists only because the generator asks *every* base type about NaN,
  including the ones where the question looks silly. Asking the silly question is the point: the
  bug was in the type where NaN "cannot happen", and hostile input is precisely the case where it
  can.

- **Deriving one language's data from the other narrows what the corpus can prove, and that is
  worth saying out loud.** The corpus proves TypeScript matches Python. It cannot prove either
  matches reality, and with a transcoded profile a `generate_profile.py` bug is identically wrong
  in both. The fitdecode oracle is the only check that points outward, which is why the ADR now
  names it rather than leaving it as tooling.

- **A principle applied without its reason is cargo cult.** F31 established "`Map` for ordered
  internals" and the F32 spec applied it to pure lookup tables where nothing iterates
  order-sensitively — costing bundle bytes and construction across 5,000 entries for a property
  nobody needed. Critique narrowed it and the invariant ("nothing may depend on iteration order")
  now ships in the generated header, so the next reader sees a decision rather than an oversight.

- **The twin-surface check works, and it works on convenience.** Both times it has fired, the
  divergence was a *helpful* extra export — `dumpsText` in F31, the registry re-export here.
  Neither was wrong code; both were a second way to say something Python says one way. That is
  precisely the drift a parity project accumulates if nothing looks for it.

- **Two gates that look redundant often are not.** Regenerate-and-diff catches staleness;
  value-parity catches a transcoder that has always been wrong the same way. Stating which failure
  each one catches, in both scripts' docstrings, is what stops a future cleanup from deleting one.

## Post-Implementation Checklist
- [x] Feature spec status updated to DONE
- [x] INDEX.md updated
- [x] DEPENDENCY_MAP.md updated
- [x] Architecture docs updated (OVERVIEW profile rows; ADR-0009 §8 rewritten)
- [x] All new behavior covered by unit tests (298 total) and differential vectors
- [x] Every new drop/repair/reinterpretation emits provenance — N/A: data layer, no data path.
      The nearest hazard is a *wrong* table silently mis-scaling values, which no provenance entry
      could record; guarded upstream by the fitdecode oracle and at emission by `repr` floats
- [x] Determinism verified (regeneration byte-identical; value parity across 1,382 fields)
- [ ] Skills assessed and updated (`/post-impl-review`)
