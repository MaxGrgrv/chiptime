# Feature: F31 — JS scaffolding, canonical JSON, number kernel, parity harness

> Status: CRITIQUED

## Purpose

Lay the two modules every other TypeScript module will sit on, and prove they agree with Python
*before* a single FIT byte is read.

`canonical.ts` defines what "byte-identical output" means on the JS side; `numeric.ts` defines
what a number does when it rounds. These are the two places where a silent divergence would be
discovered last (somewhere in a corpus snapshot at F35, with 8,000 lines of ported code in
between) and cost the most to localize. So they ship first, differentially tested against CPython
over generated vectors, with the packaging and CI needed to run them.

Everything here is infrastructure. No FIT parsing, no npm publish.

## Context Check
- [x] `docs/PRD.md` — §6.2 (twin idiomatic implementations, corpus as contract), §13 (M3 shape decisions)
- [x] `docs/INDEX.md` — F31 is the first M3 feature; no existing JS work to duplicate
- [x] `docs/architecture/OVERVIEW.md` — `js/` mirrors `python/src/chiptime/` module-for-module
- [x] `docs/dependencies/DEPENDENCY_MAP.md` — runtime deps stay at zero in both languages
- [x] `docs/edge-case-taxonomy.md` — no parser behavior in scope (see below)
- [x] No duplication: `canonical.py` is the reference implementation, not a thing to re-derive

## Taxonomy Coverage

**None — infrastructure only.** Same posture as F2, which built `canonical.py` and the corpus
tooling: individual taxonomy items land with the features that implement their behavior (F33
onward), because a snapshot needs a parser. F31 serves contract #2 (determinism) across languages
and unblocks contract #7 (every taxonomy item → a corpus case) for the TypeScript runner.

| Taxonomy item # | Summary | Corpus case(s) planned |
|---|---|---|
| — (infrastructure) | JS package, JCS canonicalizer, number kernel, vector harness | none; corpus consumption begins at F33 |

## Requirements

### 1. `js/` package scaffolding
1. `js/package.json` — name `chiptime`, version `0.0.0` (unpublished), `"dependencies": {}`,
   ESM + CJS + `.d.ts` via an `exports` map, `engines.node >= 20`, explicit `files` allowlist, and
   a `"parity"` field naming the PyPI version whose surface this build matches (ADR-0009 §9).
2. `js/tsconfig.json` — `strict`, `ES2022` target, `isolatedModules`, `declaration`,
   `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`. Two build configs (ESM, CJS), both
   plain `tsc` — no bundler on the publish path.
3. `js/biome.json` — lint + format (the `ruff` analogue), matching the repo's existing
   line-length and quote conventions where they translate.
4. Dev dependencies only: `typescript`, `vitest`, `@biomejs/biome`, `@types/node`.
5. No `node:` import may execute at module load in `js/src` — Node-only paths are reached lazily,
   behind the path-input guard, so the package stays browser/Deno/Bun-safe (ADR-0009 §7).

### 2. `js/src/canonical.ts` — RFC 8785, the ADR-0002 number policy
6. `dumps(value: unknown): Uint8Array` — UTF-8, no whitespace, keys sorted by UTF-16 code units,
   minimal escaping per `canonical.py`. Accepts **both** plain objects and `Map<string, unknown>`
   as JSON objects; the shaping layer uses `Map` wherever internal order matters (Req 9) and must
   not have to convert on the way out. *(amendment A1)*
7. `CanonicalizationError` for values that must never reach serialization: `NaN`, `±Infinity`,
   `BigInt` (the shaping layer stringifies those, ADR-0002 §2), non-string keys, `undefined`,
   functions, symbols, and integral numbers beyond ±(2^53 − 1) — see Risk 1 for the one asymmetry
   this last rule carries.
7a. The refusal list additionally covers values `JSON.stringify` would silently mangle rather than
   reject — **contract #1 guards, not tidiness** *(amendment A2)*:
   - `Uint8Array` and other typed arrays — `JSON.stringify` emits `{"0":31,"1":139,…}`. Python's
     shaping layer hex-encodes bytes (`result.py:_json_safe`); TypeScript must do the same
     *before* serialization, and be told loudly when it forgot.
   - `Date` — `JSON.stringify` calls `toISOString()`, which always emits `.000` and would put a
     wrong timestamp into canonical output (ADR-0009 §5). `Date` must never reach `dumps`.
   - **sparse arrays / array holes** — `JSON.stringify` renders a hole as `null`, which is exactly
     the zero-vs-null confusion contract #4 exists to prevent. A hole is a bug, not an absence.
   - objects with a `toJSON` method — silently redirects serialization away from the shape the
     shaping layer built.
8. `-0` serializes as `0`. Numbers otherwise format via `String(x)`, which *is* the ES6
   `Number::toString` that `canonical.py:number()` hand-implements — the 40 lines of digit
   surgery on the Python side exist to reach this behavior, so the TS side must not reimplement
   it.
9. Object key ordering uses `Map` for any ordered internal structure. Plain objects reorder
   integer-like keys in JS; canonical output sorts keys anyway, but internals must not rely on
   insertion order silently disappearing.

### 3. `js/src/numeric.ts` — the number kernel
10. `pyRound(x)` — round-half-to-even. Verified divergence: `Math.round(2.5)` is `3` where Python
    gives `2`, and `Math.round(-0.5)` is `-0` where Python gives `0`.
11. `pyRoundN(x, n)` — Python's two-argument `round`, which rounds the **exact binary value**
    half-to-even at `n` decimal places. Two tempting shortcuts are both wrong *(amendment A3)*:
    - `Math.round(x * 10 ** n) / 10 ** n` — the multiplication introduces its own error;
      Python's `round(2.675, 2)` is `2.67`, this gives `2.68`.
    - `x.toFixed(n)` — ECMA-262 specifies exact ties round **away from zero**, Python rounds them
      **half-to-even**. Verified: `(0.125).toFixed(2)` is `"0.13"`, `round(0.125, 2)` is `0.12`.
      `toFixed` is usable only as a starting point, with an explicit exact-tie correction.
    Vectors must include `0.125`, `0.375`, `2.5`, `2.675`, `1.005`, `-0.5`, `-0.125` and the
    `n = 0..4` range actually used in `insights.py` and `plausibility.py:111`.
12. `floorDiv(a, b)` and `divmod(a, b)` — Python floor semantics on negatives, for the ports of
    `civilFromUnix` and the accumulator math. JS `/` and `%` truncate toward zero.
13. Every function in this module is pure, total, and documented with the Python expression it
    mirrors.
14. `numeric.ts` is **internal**: absent from the `exports` map, not part of the published API
    surface (Python has no such module — it uses the stdlib) *(amendment A5)*.
15. `mean` / `median` / `pstdev` are **deferred to F37** with the analytics layer that calls them
    *(amendment A4)* — see `docs/BACKLOG.md`. Their only call sites are `intervals.py:186` and
    `:403`; specifying an exact-rational `pstdev` six features before its first caller means
    validating it against invented vectors instead of real ones. The module and the harness are
    built here; those three functions arrive with their call sites.

### 4. Differential parity harness
16. `scripts/gen_parity_vectors.py` — emits `js/test/vectors/*.json`: input values paired with the
    exact output CPython produces, for both modules. Deterministic; committed.
17. Vector coverage: float edges (`5e-324`, `1e-7`, `1e21`, `2^53 ± 1`, `-0.0`, values whose
    shortest repr changes form), strings (surrogate pairs, lone surrogates, combining marks,
    `\x00`–`\x1f`, keys that sort differently by code point than by code unit), nested
    structures, and for `numeric.ts` a spread of `.5` boundaries and adversarial `roundN` inputs.
18. `vitest` suites assert TS output equals the recorded CPython output exactly.
19. CI regenerates the vectors and fails on any diff, so a Python-side behavior change cannot
    silently invalidate the recorded contract.

### 5. Guards and CI
20. A repo check (grep-based, in `/verify` and CI) fails on `Math.round` anywhere in `js/src`
    outside `numeric.ts`. Zero-dependency, obvious, and it does the job a lint plugin would.
21. CI gains a `js` job — Biome check, `tsc --noEmit`, `vitest` — on ubuntu + macOS, Node 20 + 22.
22. CI gains a `parity-vectors` job — regenerate, `git diff --exit-code`.
23. A packaging smoke check mirroring `package-smoke`: build, pack, install the tarball into a
    clean directory, and import it from Node ESM *and* Node CJS.

## Acceptance Criteria
- [ ] `dumps()` output is byte-identical to `canonical.dumps()` for every committed vector
- [ ] `numeric.ts` matches CPython for every committed vector across `pyRound`, `pyRoundN`,
      `floorDiv`, `divmod` — including the exact-tie cases that defeat `toFixed`
- [ ] `dumps()` refuses every class in Req 7/7a; a `Uint8Array`, `Date`, array hole or
      `toJSON` object reaching serialization is a test failure, not a formatting question
- [ ] `dumps()` treats `Map<string, unknown>` and plain objects identically
- [ ] `CanonicalizationError` is raised for each refused value class, matching `canonical.py`
- [ ] `tsc --noEmit` clean under the strict config; Biome clean; `vitest` green
- [ ] The packed tarball imports cleanly from Node ESM and Node CJS; no `node:` import executes
      at module load
- [ ] `grep` guard green: no `Math.round` in `js/src` outside `numeric.ts`
- [ ] CI green on ubuntu + macOS × Node 20 + 22
- [ ] Vector regeneration produces no diff
- [ ] Per-mode behavior: **N/A** — no parsing in scope, modes appear at F34

## Public API Impact

**None.** Nothing is published to npm and no Python surface changes. `scripts/gen_parity_vectors.py`
is new dev tooling. The canonical JSON schema is untouched — F31 implements the existing
`chiptime_schema: 1` contract in a second language, it does not extend it.

## Architectural Placement

- `js/src/canonical.ts` → **output** layer (twin of `chiptime.canonical`)
- `js/src/numeric.ts` → **new leaf module**, no analogue in Python (where the stdlib fills the
  role). It sits below everything and imports nothing.
- `scripts/gen_parity_vectors.py` → tooling, outside both packages

## Proposed Approach

Per [ADR-0009](../architecture/adrs/0009-cross-language-parity.md) §2–§4 and
[ADR-0002](../architecture/adrs/0002-canonical-json.md).

1. Scaffold `js/` and get an empty `vitest` run green in CI first — establish the loop before
   writing logic into it.
2. Port `canonical.py` structurally (same function boundaries, same refusal points), then delete
   the float-formatting body in favor of `String(x)` and prove the equivalence by vectors rather
   than by argument.
3. Write `numeric.ts` from the CPython source semantics, not from its docstrings — particularly
   `pstdev`, where the exact-rational reduction is the whole point.
4. Generate vectors, watch them fail, fix TS. Any vector where *Python* turns out to be the odd
   one gets escalated per ADR-0009 §1 rather than accommodated.

## Critique & Assessment

_Assessed 2026-08-21. Three of the spec's own claims were checked against CPython and Node before
assessing; all three held, and one produced a new required amendment (A3)._

### Necessity — justified
Without `canonical.ts` no TypeScript module can be corpus-gated, and the corpus is the entire
parity mechanism (ADR-0009 §1). Without `numeric.ts` the port silently inherits JS rounding, which
is wrong at every `.5`. Neither duplicates existing work: `canonical.py` is the *reference* for the
port, not a competitor to it. Deferring either doesn't avoid the work — it relocates its
divergences to F35, where ~8,000 lines of ported code sit between the cause and the failing
snapshot. No PRD non-goal is touched; the zero-runtime-dependency contract is preserved in both
languages.

### Placement — correct, with one deliberate exception
`canonical.ts` sits in the **output** layer, exactly mirroring `chiptime.canonical`. `numeric.ts`
is a **new leaf** with no Python analogue (there, the stdlib fills the role), and it therefore
breaks the "module-for-module mirror" rule stated in OVERVIEW. That break is correct — the
alternative is scattering rounding helpers across call sites, where they drift — but it must be
*recorded* as an exception rather than discovered later, and the module must stay off the public
`exports` map (amendment A5). `canonical.ts` imports nothing, including `numeric.ts`: number
formatting is `String(x)`, not rounding. No cycles.

### Approach — sound; three gaps found

**Gap 1 — `Map` was required for internals but unusable at the boundary.** Requirement 9 mandates
`Map` for ordered internal structures (correctly: JS objects reorder integer-like keys), but
`dumps()` was specified to accept only plain objects, forcing a conversion pass on every output —
which is both wasteful and an opportunity to lose order. Fixed by amendment A1.

**Gap 2 — the refusal list guarded against the wrong failure mode.** It covered values
`JSON.stringify` *rejects*. The dangerous class is the one `JSON.stringify` silently **mangles**:
a `Uint8Array` becomes `{"0":31,…}`, a `Date` becomes an ISO string with a spurious `.000`
(ADR-0009 §5), an array hole becomes `null` — which is precisely the zero-vs-null confusion
contract #4 exists to prevent — and a stray `toJSON` redirects serialization away from the shape
the shaping layer built. Every one of those is silent data corruption reaching canonical output
with no provenance: a contract #1 violation the serializer is the last line of defense against.
Fixed by amendment A2.

**Gap 3 — `pyRoundN` had one named trap and needed two.** The spec correctly rejected
`Math.round(x * 10 ** n) / 10 ** n`. It did not name `toFixed`, which is the shortcut an
implementer would actually reach for and which is wrong in a subtler way: ECMA-262 rounds exact
ties **away from zero**, Python rounds them **half-to-even**. Verified — `(0.125).toFixed(2)` is
`"0.13"`, `round(0.125, 2)` is `0.12`. Fixed by amendment A3, with the tie cases pinned into the
required vectors.

**Alternatives considered.**
1. *Write `canonical.ts` and `numeric.ts` lazily, as F33/F35 need them.* Cheaper to start,
   strictly worse to debug: a canonicalizer bug then presents as "case 41 of 72 differs by one
   byte" rather than "vector 812 differs". Rejected.
2. *Transpile `canonical.py` mechanically.* Guarantees structural parity, produces unidiomatic
   output on the module most likely to be read by contributors evaluating the port, and cannot
   express the `String(x)` simplification that removes 40 lines of digit surgery. Rejected
   (consistent with ADR-0009's rejection of whole-source transpilation).
3. *Reuse an existing JCS package from npm.* Would violate the zero-runtime-dependency contract
   for ~60 lines of code, and would pin the determinism contract to a third party's release
   cadence. Rejected.
4. *ESM-only, dropping the CJS build.* Halves the packaging work and the `exports`-map surface,
   but cuts off CJS consumers of a library whose whole adoption argument is "no friction".
   Rejected; the dual `tsc` pass and its per-directory `{"type": …}` shims are a known-fiddly
   area to call out in the implementation doc.

**What could go wrong at scale.** `dumps()` recurses, and canonical output for an ultra-length
activity is wide (8,000+ element streams) but shallow (~6 levels) — width is iterative, so stack
depth is bounded by shape, not size. A pathological depth would raise in both languages, differing
only in the exception type; the shaping layer bounds depth, so this is noted, not guarded.
Per-number `String(x)` in the hot loop is the same cost profile as Python's `number()`; F31 sets
no performance gate, and the perf pass has its own precedent (F20).

### Contract check
- **Silent loss** — this was the sharpest finding. Gap 2's four mangling paths would each put
  wrong data into canonical output with no provenance entry. The serializer cannot emit provenance
  (it has no access to it), so refusal is the only correct behavior, and amendment A2 makes it so.
- **Determinism** — key ordering (UTF-16 code units, which *is* JS's default string comparator),
  `-0 → 0`, and ES6 number formatting are all specified and vector-gated. `Map` acceptance removes
  a conversion step that could reorder.
- **Sentinels & zero-vs-null** — no decoding in scope, but the array-hole refusal (A2) protects
  the zero-vs-null invariant at the serialization boundary.
- **Modes** — correctly N/A; modes appear at F34. Stated explicitly in the acceptance criteria
  rather than left blank.
- **Errors** — `CanonicalizationError` is an internal bug guard with no code or suggestion,
  matching `canonical.py`'s `ValueError` subclass. It must never reach a user; if it ever does,
  that is the bug, not the message.
- **Corpus** — "none — infrastructure only" is the honest answer and matches F2's precedent.

### Dependency analysis
Depends on F1/F2 conventions and ADR-0002/0009; no code dependency on the Python package.
`numeric.ts` is a leaf; `canonical.ts` imports nothing. No cycles, no coupling of things that
should be independent.

**Blast radius is total but loud.** A `canonical.ts` defect fails every corpus case at F35 — the
worst possible breadth, the best possible signal. The genuinely dangerous case is a *narrow*
`numeric.ts` defect: `pyRoundN` has exactly one core-path caller (`plausibility.py:111`), so a bug
in it could pass F35's full-corpus gate and only surface at F37. That asymmetry is the argument
for the vector harness being broad rather than call-site-driven, and it is why amendment A3 pins
specific tie values instead of trusting a range.

### Simplification — one cut taken
`mean` / `median` / `pstdev` are **deferred to F37** (amendment A4, logged to BACKLOG). Their only
call sites are `intervals.py:186` and `:403`, six features downstream. `pstdev` is the expensive
one — an exact-rational reduction over `BigInt` — and specifying it now means validating it
against invented vectors rather than the real distributions its caller produces. The module and
the harness are built here; those three functions arrive with the code that calls them.

Two requirements were examined and **kept**: the pack-and-import smoke check (Req 23) tests
scaffolding rather than product, but catches `exports`-map mistakes while there is one module to
debug instead of thirty; and the dual ESM/CJS build costs real fiddliness for real reach.

The `Math.round` grep guard (Req 20) wants siblings — bans on `Date` outside the timestamp
formatter, and on comparator-less `.sort()` over numbers. Both belong with the code they would
guard (F33, F35); logged to BACKLOG rather than speculatively added here.

### Final decision: **APPROVE** — with amendments A1–A5 applied above

The plan is necessary, correctly placed, and simpler than the alternatives. Three real gaps were
found and fixed in the requirements rather than left as review notes, and one speculative scope
cut was taken. Ready for `/implement`.

## Dependencies
- **Depends on:** F1 (repo conventions, CI shape), F2 (`canonical.py` is the reference),
  ADR-0002, ADR-0009
- **Depended on by:** F32–F41 (every TypeScript module)

## Related
- ADR: [0009](../architecture/adrs/0009-cross-language-parity.md), [0002](../architecture/adrs/0002-canonical-json.md)
- Plan: [../m3-typescript-plan.md](../m3-typescript-plan.md)
- Implementation: `../implementation/f31-js-scaffolding-canonical-numeric.md` (created by `/implement`)
