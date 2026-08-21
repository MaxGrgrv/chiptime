# Implementation: F31 — JS scaffolding, canonical JSON, number kernel, parity harness

> Feature Spec: [../features/f31-js-scaffolding-canonical-numeric.md](../features/f31-js-scaffolding-canonical-numeric.md)
> Plan: [../m3-typescript-plan.md](../m3-typescript-plan.md) · Contract: [ADR-0009](../architecture/adrs/0009-cross-language-parity.md)

## Summary

The `js/` package exists, builds ESM + CJS from plain `tsc` with zero runtime dependencies, and
carries the two modules everything else in M3 will sit on: `canonical.ts` (RFC 8785, the twin of
`canonical.py`) and `numeric.ts` (Python's rounding semantics, ported explicitly). Both are
differentially tested against CPython over 165 generated vectors, wired into CI on two operating
systems and two Node majors.

No FIT parsing, nothing published to npm. What shipped is the determinism contract in a second
language, proven rather than asserted.

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `js/package.json` | Added | Zero runtime deps, ESM+CJS exports map, `files` allowlist, `parity` field, `private: true` until F34 |
| `js/tsconfig.json`, `js/tsconfig.esm.json`, `js/tsconfig.cjs.json` | Added | Strict TS; `lib: ["ES2022"]` only — no DOM, no node types in `src` |
| `js/biome.json`, `js/vitest.config.ts` | Added | Lint/format (the `ruff` analogue) and a shuffle-free test runner |
| `js/src/canonical.ts` | Added | JCS serializer, number policy, UTF-8 encoder, the refusal set |
| `js/src/numeric.ts` | Added | `pyRound`, `pyRoundN`, `floorDiv`, `divmod` — internal, off the exports map |
| `js/src/index.ts` | Added | Public surface: `dumps`, `dumpsText`, `formatNumber`, `CanonicalizationError`, `MAX_SAFE_INT` |
| `js/test/canonical.test.ts` | Added | 77 tests: vectors, the mangling refusals, `Map` equivalence, UTF-8, determinism |
| `js/test/numeric.test.ts` | Added | 88 tests: vectors plus the shortcut-defeating cases |
| `js/test/vectors.ts`, `js/test/vectors/*.json` | Added | Generated vectors + their loader |
| `js/scripts/guards.mjs` | Added | Grep guard: `Math.round` banned outside `numeric.ts` |
| `js/scripts/determinism.mjs` | Added | Hashes every vector's output; run twice from separate processes in CI, and compared against CPython's recorded bytes |
| `js/scripts/finish-build.mjs` | Added | Writes `dist/cjs/package.json` — the CJS type shim |
| `js/scripts/smoke.sh` | Added | Pack, install into a clean dir, import from ESM and CJS, assert no `node:` imports |
| `js/README.md`, `js/LICENSE` | Added | Parity table and the pre-release status; MIT copied from root |
| `scripts/gen_parity_vectors.py` | Added | Emits the vectors from CPython; deterministic; CI regenerates and diffs |
| `.githooks/pre-push` | Modified | Extended with the JS gates so the local last line still matches CI; skips cleanly when `js/node_modules` is absent |
| `.github/workflows/ci.yml` | Modified | Three jobs: `js` (2 OS × Node 20/22), `js-package-smoke`, `parity-vectors` |

## Corpus Cases Added

None — infrastructure only, as specified. The vectors under `js/test/vectors/` play the role the
corpus plays for parsing features: generated from a committed script, never hand-edited, and
regenerated in CI so they cannot silently drift. Corpus consumption begins at F33.

## Key Implementation Decisions

1. **Inputs are stored as JSON *text*, not as decoded values.** Each side parses the same string
   with its own JSON reader and serializes with its own canonicalizer. Storing decoded values
   would have meant inventing an interchange encoding and testing that instead of the thing that
   actually has to match.

2. **Hand-rolled UTF-8 encoder instead of `TextEncoder`.** Two reasons, one of which was not in
   the spec: it keeps `src/` free of any environment lib (no DOM, no `node:`), *and*
   `TextEncoder` silently replaces an unpaired surrogate with U+FFFD where Python's
   `.encode("utf-8")` raises. A silent character substitution on an output path is exactly the
   class of bug the refusal set exists to prevent, so the encoder refuses and both
   implementations fail on the same input.

3. **The refusal set is a whitelist, not a blacklist.** `write()` accepts null, boolean, string,
   number, `Array`, `Map`, and plain objects; everything else falls through to a refusal. This
   mirrors `canonical.py`, which accepts only `None/bool/int/float/str/list/dict`, and means a
   value class nobody anticipated is refused by default rather than serialized by accident.

4. **`refuseMangled()` names its hazards.** Rather than one generic "unserializable type", the
   `Uint8Array`, `Date`, `toJSON` and sparse-array cases each carry a message saying what
   `JSON.stringify` would have done instead. The tests assert the hazard alongside the refusal —
   `expect(JSON.stringify(new Uint8Array([31, 139]))).toBe('{"0":31,"1":139}')` — so the reason
   the guard exists is visible to whoever next reads the test.

5. **`pyRoundN` rounds in integer arithmetic.** The double is decomposed to its exact
   `mantissa × 2^exp` form via `DataView`, scaled by `10^n` as `BigInt`, and rounded half-to-even
   with an exact tie test. Both float shortcuts are wrong (see Lessons), and only exact arithmetic
   makes ties unambiguous.

6. **Guards are a grep, not a lint plugin.** `scripts/guards.mjs` is 40 lines, has no
   dependencies, skips comment lines so prose about the ban does not trip it, and prints a
   sentence explaining *why* rather than a rule id. It was verified to exit 1 on a probe file.

## Deviations from Spec

1. **The asymmetry band is wider than Risk 1 described, and three vectors moved.** The spec framed
   the integral-float asymmetry as an edge case at the 2^53 boundary. It is not an edge: **every
   finite double at or above 2^53 is integral**, so TypeScript's value-based guard refuses the
   entire range `[2^53, 1.797e308]` while Python's type-based guard accepts all of it as floats.
   The vector harness found this on its first run — `1.7976931348623157e308`,
   `1.00000000000001e20` and `9007199254740991.5` (which rounds to an integral double) were
   written as "ok" vectors and were refused. They are now recorded in `canonical-asymmetry.json`
   with the corrected note. No corpus snapshot contains a number in this band, so the asymmetry
   stays unreachable in practice — but it is a range, not a boundary, and the docs now say so.

2. **`pyRound` needed an explicit negative-zero normalization** that the spec did not anticipate.
   Python's `round(x)` returns an `int`, and an int has no `-0`: `round(-0.0)` is `0`.
   `Math.floor(-0)` is `-0`, so the straightforward port returned `-0` and failed its vector.
   Caught by comparing with `Object.is` rather than `===` — worth keeping in every numeric
   comparison in this port, since `0 === -0` is true and would have hidden it.

3. **A `check` script was added** (`lint && typecheck && guards && test`) so `/verify` and CI run
   the same four things in the same order.

### Fixed during `/verify`

4. **`dumpsText` was exported from `index.ts` and should not have been.** It is a test and
   diagnostic convenience with no `chiptime.canonical` counterpart, and ADR-0009 §2 says the
   public surface mirrors Python — one name per concept, and no concept the twin does not have.
   Moved off the package export; it stays importable from the module, which is all the tests
   needed. The published surface is now exactly `dumps`, `formatNumber`, `CanonicalizationError`,
   `MAX_SAFE_INT`, mirroring `canonical.py`'s `dumps`, `number`, `CanonicalizationError`,
   `MAX_SAFE_INT` under the documented camelCase mapping.

5. **Cross-process determinism had no permanent gate.** The vitest suite compares each vector
   against CPython inside a single process, which does not test contract #2's "same bytes across
   runs and processes" half — the Python side gets that from its `cross-os-determinism` job.
   `js/scripts/determinism.mjs` now hashes every vector's output from the *built* artifact; CI runs
   it twice in separate processes, diffs the output, and prints both hashes. The two currently
   agree with each other and with CPython:

   ```
   typescript: fcf24974da5e8438d94c5961f6a6c3cd69703ce4ccdb8557d6e29dcef7e199b3
   cpython:    fcf24974da5e8438d94c5961f6a6c3cd69703ce4ccdb8557d6e29dcef7e199b3
   ```

## Lessons Learned

- **The harness paid for itself before the module was finished.** Two of the three bugs above were
  found by vectors on the first run, not by review — and both were in the *spec's own assumptions*
  rather than in the code. That is the argument for building the differential harness first rather
  than alongside: it audits the plan, not just the implementation.

- **`toFixed` is the trap worth documenting loudest.** It is the obvious shortcut for `round(x, n)`,
  it is right for most inputs, and it is wrong on exactly the values that appear in rounding tests:
  ECMA-262 rounds exact ties away from zero, Python rounds them half-to-even. `(0.125).toFixed(2)`
  is `"0.13"`; `round(0.125, 2)` is `0.12`. The test asserts both, so the next reader sees the
  divergence rather than the conclusion.

- **`Object.is`, not `===`, for every numeric assertion in this port.** `0 === -0` is true, which
  silently hides sign bugs on a value that reaches canonical output.

- **The tests should show the hazard, not just the guard.** Asserting what `JSON.stringify` *would*
  have emitted next to the refusal turns a rule into an explanation, and costs one line.

- **For `/verify`:** the existing "never pipe checkers through `tail`" lesson bit again — `npm run
  guards | tail` reported exit 0 while the guard had exited 1. Every check in this feature was
  re-run bare with `$?` captured.

- **Rewriting a doc section can orphan its cross-references.** `/critique` replaced the whole
  "Critique & Assessment" block, which deleted the named "Risk 1" that Requirement 7 and a
  `canonical.ts` comment both point at. Nothing failed — dangling prose references are invisible to
  every gate we run. Caught by hand and folded into `/critique` as a rule.

- **A twin makes API drift a thing you can check, so check it.** Listing both export surfaces side
  by side took one command and caught `dumpsText`. That check now lives in `/verify` and gets more
  valuable with every feature, since the surfaces only grow.

- **A bilingual repo needs its local gate updated the day the second language lands.** The
  pre-push hook was Python-only and would have let a red JS build through — the one place the
  "last line of defense" comment promises it will not. Extending it immediately caught a bug *in
  the extension*: `npm run determinism` prints build chatter before the hashes, so capturing it
  twice compared chatter, not output. Build once, run the checker twice.

- **Release-facing docs go stale where no gate looks.** The root README still claimed `0.4.0`,
  `273 tests`, and `71 corpus cases` — three M2.8 features shipped past it. Corrected here from
  measured values; worth a `/doc-check` assertion that README's version matches
  `chiptime.__version__` and its counts match reality.

## Post-Implementation Checklist
- [x] Feature spec status updated to DONE
- [x] INDEX.md updated
- [x] DEPENDENCY_MAP.md updated
- [x] Architecture docs updated (OVERVIEW gains the `js/` module table)
- [x] All new behavior covered by unit tests (165) and differential vectors
- [x] Every new drop/repair/reinterpretation emits provenance — N/A: no data path in this feature;
      the serializer *refuses* rather than reinterprets, which is the contract-#1-safe direction
- [x] Determinism verified (repeated calls byte-identical; key order independent of insertion order)
- [x] Skills assessed and updated — `/verify` gained the TypeScript gates (Biome, `tsc`, source
      guards, vitest, pack smoke), the cross-language determinism step, the vector-freshness step,
      and a twin-surface check; `/critique` gained a rule against orphaning named cross-references
      when it rewrites a spec section
