# M3 — the TypeScript twin on npm

> Status: **PLANNED** · created 2026-08-21 · governed by [ADR-0009](architecture/adrs/0009-cross-language-parity.md)
> Prerequisite: M2.8 in progress (F26–F28 shipped; F29 `convert`, F30 `merge` queued). M3 features are numbered **F31–F41**.

## Goal

`chiptime` on npm: a twin implementation with **full feature parity** to the Python package —
same parsing, same recovery, same canonical JSON bytes, same error/provenance codes, same CLI
verbs and exit codes — consuming the same `corpus/` as its conformance contract.

Parity is not a claim we make in a README. It is three CI gates:

1. **Conformance** — every corpus case produces byte-identical `expected.json` from TypeScript.
2. **Profile parity** — both generated profile tables digest-match (`check_profile_parity.py`).
3. **Cross-implementation diff** — a harness runs both binaries over every case and every CLI
   invocation and diffs stdout bytes.

## Shape

```
js/
  package.json          # name "chiptime", zero runtime deps, ESM + CJS, types
  tsconfig.json         # strict, ES2022 target, isolatedModules
  src/
    index.ts            #  ← mirrors python/src/chiptime/__init__.py
    api.ts  intake.ts  inflate.ts  frames.ts  decode.ts  message.ts
    model.ts  result.ts  canonical.ts  numeric.ts  errors.ts
    encode.ts  repair.ts  validate.ts  edit.ts  trim.ts  privacy.ts  cli.ts
    profile/{index,base-types,core,registry,generated}.ts
    semantics/{build,timers,gaps,reconcile,plausibility}.ts
    metrics/{index,basics,zones,sports,pacing,intervals,load,insights,settings}.ts
  test/
    conformance/corpus.test.ts    #  ← port of tests/conformance/test_corpus.py
    *.test.ts                     #  ← per-module, mirroring python/tests/
```

Module-for-module with `python/src/chiptime/`, so a reviewer can diff the two trees side by side
and so a Python change has an obvious TypeScript address. Tooling: TypeScript + vitest + Biome
(dev dependencies only). Node ≥ 20; browser, Deno and Bun supported by construction — the package
touches no runtime API beyond `Uint8Array`, `DataView` and `TextDecoder`, with `node:fs` reached
only behind a path-input guard.

## Feature breakdown

Each feature runs the full lifecycle (`/plan-feature` → `/critique` → `/implement` → `/verify` →
`/post-impl-review`) and commits on its own, as every Python feature did.

| # | Feature | Mirrors | Gate | npm |
|---|---|---|---|---|
| **F31** | JS scaffolding, canonical JSON, number kernel, parity harness | F1, F2 | `canonical.ts` == `canonical.py` over generated vectors; `numeric.ts` differential-tested against CPython | — |
| **F32** | Profile tables: dual emitter + base types + vendor registry | F18, F6 | `check_profile_parity.py` digest equality | — |
| **F33** | Frames + decode core (base types, endianness, compressed timestamps, components, subfields, accumulators, dev fields) | F3, F6, F22 | message-level parity on `clean/`, `protocol/`, `devfields/` | — |
| **F34** | Intake + inflate + recovery + modes + `ParseResult` shaping + `parse`/`inspect`/`codes` CLI | F4, F5, F11, F15 | `container/`, `structural/` cases; NOT_FIT routing; exit codes | `0.0.x` preview |
| **F35** | Semantics: model, build, timers, gaps, reconcile, plausibility | F7–F10, F17, F21 | **all 72 public cases byte-identical, all three modes, double-parse determinism** | **`0.1.0`** |
| **F36** | Encoder + `repair` + platform `validate` profiles | F12–F14 | round-trip identity; repair output byte-identical to Python's | **`0.2.0`** |
| **F37** | Analytics layer: metrics + `analyze` | F23–F25 | `analyze` stdout byte-identical per corpus case | **`0.4.0`** |
| **F38** | `edit` — metadata surgery | F26 | edited bytes identical to Python's; validated round-trip | **`0.5.0`** |
| **F39** | `trim` — crop + rebuild | F27 | trimmed bytes identical; rebuilt totals identical | **`0.6.0`** |
| **F40** | `reveal` + `scrub` — privacy | F28 | report + scrubbed bytes identical | **`0.7.0`** |
| **F41** | Browser build, docs-site JS tabs, parity CI hardening, parity release | F11, F16 | full harness green on every case × every verb | parity tag |

npm skips `0.3.0`: Python `0.3.0` (M2.5) and the M2.6 hardening were internal — soak fixes, full
profile generation, the perf pass, real-file corpus promotion. The port inherits those behaviors
from the code it mirrors, so there is no distinct surface to stage. See ADR-0009 §9.

## Why this order

Dependency-forced, not preference. `canonical.ts` and `numeric.ts` (F31) sit under everything and
are the two modules where a silent divergence would be discovered last and cost most — so they
ship first, with differential tests, before any FIT byte is read. The profile (F32) is pure data
under decode. Decode (F33) cannot be corpus-gated end-to-end until intake and result shaping
exist (F34), which is why F34 carries the first runnable CLI. F35 is the milestone that matters:
the moment the corpus goes green, "parity" stops being a plan.

The write verbs (F38–F40) come after analytics (F37) only to keep the version mirror legible;
they are independent of each other and could be reordered without cost.

## Known hazards, and where each is handled

| Hazard | Where it lands | Handling |
|---|---|---|
| `Math.round` is half-up; Python's is half-to-even | `repair.py:242`, `insights.py` ×12, `_basics.py:93` | `pyRound` in F31; `Math.round` banned by lint |
| `round(x, n)` rounds on decimal repr | `insights.py`, `plausibility.py:111` | `pyRoundN` in F31 |
| `statistics.pstdev` uses exact rationals | `intervals.py:403` | exact-rational port over `BigInt` in F31 |
| 64-bit base types exceed `Number.MAX_SAFE_INTEGER` | `decode.py`, `result.py:240` | `BigInt` decode + existing ADR-0002 string policy, F33 |
| `Date.toISOString()` always emits `.000` | every timestamp in output | integer `civilFromUnix` formatter, `Date` off all output paths, F33 |
| libm vs V8 for `sin`/`cos`/`asin`/`exp` | `plausibility.py:26`, `load.py:112` | ADR-0009 §6: same formulation, rounding absorbs, corpus gates |
| JS objects reorder integer-like keys | any ordered map in shaping | `Map` for ordered internals; canonical output sorts keys anyway |
| Browsers have no synchronous decompression | `intake.py` gzip/zip | own `inflate.ts`, F34 — keeps `parse()` sync everywhere |
| Python `//` floors; JS `/` does not | `civilFromUnix`, accumulator math | explicit `Math.floor`/`BigInt` division at every port site, F31/F33 |

## Out of scope for M3

- Corpus **generation** tooling stays Python-only. `corpus/tools/*` is deliberately independent of
  `chiptime` (ADR-0001 §3) and TypeScript gains nothing by duplicating a fixture writer; the port
  consumes committed inputs.
- `[pandas]`-equivalent dataframe integration.
- Any feature not yet shipped in Python. F29 `convert` and F30 `merge` land in Python first and
  reach npm afterwards, per ADR-0009 §1.

## Related

- [ADR-0009](architecture/adrs/0009-cross-language-parity.md) — the parity contract
- [ADR-0001](architecture/adrs/0001-corpus-format.md) — the corpus as the cross-language contract
- [ADR-0002](architecture/adrs/0002-canonical-json.md) — canonical JSON and the 64-bit policy
- [ADR-0004](architecture/adrs/0004-profile-strategy.md) — profile generation, never SDK material
- [PRD.md §11](PRD.md) — roadmap
