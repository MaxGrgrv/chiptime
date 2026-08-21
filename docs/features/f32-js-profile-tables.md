# Feature: F32 — Profile tables for TypeScript

> Status: DONE

## Purpose

Give the TypeScript decoder the data it decodes *with*: base types, the merged
message/enum tables, and the known-vendor developer-field registry.

This is the second and last M3 feature with no FIT bytes in it. Everything from F33 on reads
files; nothing can read a file without knowing that global message 20 is `record`, that field 253
is `timestamp`, that `uint16`'s invalid sentinel is `0xFFFF`, or that altitude is `/5 - 500`.

The interesting question is not how to write the tables down. It is **where the TypeScript tables
come from**, because the answer determines whether the two languages can ever disagree about what
a FIT file says.

## Context Check
- [x] `docs/PRD.md` — §6.1 (profile is a data-only leaf, unknown-tolerant), §8 (licensing: never
      commit SDK material), §13 (M3 shape decisions)
- [x] `docs/INDEX.md` — F18 generated the Python tables; F6 built the vendor registry; F31 is the
      only TypeScript work so far
- [x] `docs/architecture/OVERVIEW.md` — `profile` is a leaf in both trees; `js/src/profile/*` is
      listed as F32
- [x] `docs/dependencies/DEPENDENCY_MAP.md` — `profile` imports nothing; runtime deps stay zero
- [x] `docs/edge-case-taxonomy.md` — #26 (sentinels), #27 (scale/offset), #22d (vendor dev fields),
      contract #6 (unknown ≠ invalid)
- [x] No duplication: the SDK→Python step (F18) is untouched; this feature adds a step *after* it

## Taxonomy Coverage

**None directly — data layer.** The tables carry the facts that F33's decoder uses to satisfy #26,
#27 and #22d; the corpus cases for those items land with F33, which is the first feature that can
produce a snapshot. The one behavior F32 owns outright is **contract #6 (unknown ≠ invalid)**: a
table that lacks an entry must yield `unknown_*`, never an error, so a stale profile can never
crash a decode.

| Taxonomy item # | Summary | Corpus case(s) planned |
|---|---|---|
| — (data layer) | Base types, merged message/enum tables, vendor registry | none; F33 carries the decode cases that exercise them |
| contract #6 | Unknown message/field/enum tolerated | unit tests here; corpus at F33 |

## Requirements

### 1. `js/src/profile/base-types.ts` — hand-ported, not generated
1. The 17 base types with `byte`, `name`, `size`, and `invalid` sentinel, plus `BASE_TYPES` /
   `BASE_TYPES_BY_NAME` lookups and `isInvalid(bt, value)`, mirroring `base_types.py`.
2. **`struct_code` does not port.** It names a Python `struct` format character. The TypeScript
   table carries the `DataView` accessor instead (`getUint16`, `getFloat32`, …) plus signedness
   and width, which is the same fact in the form this runtime can use.
3. **Sentinels are `bigint` where they must be.** `float64`'s invalid is `0xFFFFFFFFFFFFFFFF` and
   `uint64`'s likewise — both beyond `Number.MAX_SAFE_INTEGER`. The 64-bit rows carry `bigint`
   sentinels (ADR-0009 §4); the rest carry `number`.
4. `isInvalid` reproduces the Python function exactly, including the signed-sentinel table and the
   NaN treatment for float types.
5. This file is **hand-written and reviewed**, not generated — it is 17 rows of protocol constants
   that change when the FIT spec does, i.e. approximately never, and a generator for it would be
   more code than the table.

### 2. `js/src/profile/generated.ts` — transcoded from the Python tables
6. `scripts/gen_profile_ts.py` imports `chiptime.profile` and emits `js/src/profile/generated.ts`.
   It reads the **merged** `MESSAGES` and `ENUMS` (see Proposed Approach for why), plus
   `GENERATED_SDK_VERSION`, and writes them as TypeScript data with a provenance header stating
   **SDK-version-plus-core**, not the SDK version alone *(amendment B1)*: the merged table is
   generated breadth *overridden by* hand-authored entries, and a header claiming pure SDK
   provenance would misdescribe a file whose accuracy claims are load-bearing under ADR-0004.
   It names both Python sources, the merge policy, the licensing note, and the non-affiliation
   statement.
7. Deterministic: same Python tables → byte-identical TypeScript, sorted, no wall clock.
8. The emitted module is data only — no logic, no imports beyond the `FieldDef`/`MessageDef` types.
9. `scale`/`offset` are emitted as numbers; the semicircle scale is emitted as the literal
   `2 ** 31 / 180` so the constant is visibly the same expression in both languages (#27).
9a. **Floats emit via Python `repr`, strings via `json.dumps`** *(amendment B4)*. Not a
   precaution: the profile carries genuinely non-integral scales — `0.7111111`, `1.024`,
   `28.57143`, `10430.38`, `11930464.711111112` — and a scale that shifts by one ULP silently
   mis-scales every value in its field. `repr` is shortest-round-trip and JavaScript parses the
   result back to the identical double, which is the same equivalence F31 settled by vectors.
   Enum labels are mixed-case identifiers (`fenix6S`, `Edge_130`, `india_zone_IIIA`), so escaping
   must be principled rather than assumed-ASCII.

### 3. `js/src/profile/index.ts` and `core.ts`
10. `core.ts` carries the `FieldDef` / `MessageDef` types and `SEMICIRCLE_SCALE`. It does **not**
    carry a TypeScript copy of the hand-authored core tables — those are already inside the merged
    output (Requirement 6).
11. `index.ts` re-exports `MESSAGES`, `ENUMS`, `BASE_TYPES`, `BASE_TYPES_BY_NAME`,
    `SEMICIRCLE_SCALE`, `isInvalid`, `GENERATED_SDK_VERSION` — the same names `profile/__init__.py`
    exports, under the ADR-0009 §2 camelCase mapping.
12. **Lookup tables are plain null-prototype objects; `Map` is reserved for where order matters**
    *(amendment B2)*. F31's Req 9 mandated `Map` for ordered internals, and applying it blanket
    here would be cargo-culting it: these tables are pure key lookups, nothing iterates them in a
    way order affects, and `new Map([[...]])` wrappers cost both bundle bytes and load-time
    construction across ~5,000 entries. The invariant is stated in the emitted header — *nothing
    may depend on the iteration order of these tables* — so that a future reader who needs
    ordered iteration reaches for a sorted key list rather than assuming one.

### 4. `js/src/profile/registry.ts` — vendor developer fields
13. Hand-ported: 8 rows, `VendorField`, and `lookup(vendor, fieldName)` with the same
    lowercase/strip normalization. Small, hand-maintained, and an M4 growth area in both
    languages — generating it would couple two files that want independent edits.

### 5. Parity gate
14. `scripts/check_profile_parity.py` digests both tables to a canonical form and requires
    equality: every message number, name, field number, field name, type, scale, offset, units,
    and every enum name/value/label. It runs `node` to dump the TypeScript side, so it compares
    *values*, not source text.
15. CI regenerates `generated.ts` and fails on any diff — the pattern F31 proved for the parity
    vectors. A maintainer who reruns `generate_profile.py` with a newer SDK and forgets the
    TypeScript step fails here rather than shipping two profiles.

## Acceptance Criteria
- [ ] `check_profile_parity.py` reports zero divergences across all 119 messages and 176 enums
- [ ] Regenerating `generated.ts` produces no diff (determinism + freshness)
- [ ] `isInvalid` agrees with Python for every base type × (sentinel, sentinel±1, 0, NaN),
      exercised by differential vectors in the F31 harness style
- [ ] Unknown tolerance: a message number, field number, and enum value absent from every table
      each resolve to `unknown_*` without throwing (contract #6)
- [ ] The 64-bit sentinels round-trip as `bigint` without precision loss
- [ ] `tsc`, Biome, guards, and vitest clean; the pack smoke still shows no `node:` import in
      `dist`
- [ ] **Built bundle size is measured and reported** in the implementation doc, raw and gzipped
      *(amendment B3)*. `generated.py` is 232 KB / 41 KB gzipped and the TypeScript twin will be
      comparable. That is acceptable for a parsing library and unacceptable to discover by
      accident, and no consumer can tree-shake past it — a complete profile is the point.
- [ ] No SDK material is committed, and no new file claims Garmin provenance (ADR-0004)
- [ ] Per-mode behavior: **N/A** — the profile is data; modes are a decode-layer policy

## Public API Impact

**None published.** `js/src/profile/*` is internal to the package at this stage; `index.ts` (the
package entry) is unchanged. New dev tooling: `scripts/gen_profile_ts.py`,
`scripts/check_profile_parity.py`. No canonical JSON schema change.

## Architectural Placement

**`profile` layer, leaf**, in both trees. `js/src/profile/*` imports nothing from the rest of
`js/src` — same rule as Python, where `profile` and `errors` are the two leaves.

## Proposed Approach

Two decisions here depart from [ADR-0009](../architecture/adrs/0009-cross-language-parity.md) §8,
which specified "one source, two emitters": `generate_profile.py` writing both `generated.py` and
`generated.ts` from the SDK in a single run. Implementing it revealed better options.

**Departure 1 — transcode from the committed Python tables, not from the SDK.**
`generated.py` is importable pure data (119 `MessageDef`s, 176 enum maps). A transcoder that
imports it and walks the objects needs no SDK, no `.xlsx` reader, and no Python-source parsing.
This matters beyond convenience:

- The SDK step stays exactly where F18 put it — a maintainer-only action requiring a local
  download that must never be committed (ADR-0004). Anyone else, and CI, can regenerate the
  TypeScript tables from a clean checkout.
- ADR-0009 §8's stated goal was that the two tables cannot drift. A dual emitter achieves that
  only if both are rerun together; a transcoder plus a CI regenerate-and-diff makes drift
  *impossible to commit*, which is stronger.

**Departure 2 — emit the merged tables, not generated-plus-core.**
Python's `profile/__init__.py` merges generated SDK breadth with a hand-authored,
fitdecode-verified core, with the core winning per field and per enum value (F18's merge policy).
Porting both tables *and* the merge logic to TypeScript would create a second implementation of a
policy that has no test of its own and whose divergence would surface as a mysterious field-name
difference at F35. Emitting the already-merged result deletes that risk: the merge stays in one
language, and TypeScript consumes its output.

The cost is provenance legibility — a reader of `generated.ts` cannot see which entries were
hand-verified. Mitigated by the emitted header, which names both Python sources and the merge
policy, and by the fact that the merge remains reviewable where it lives.

Everything else is a direct port: base types and the vendor registry are hand-written (17 rows and
8 rows respectively, both protocol constants rather than derived data), and `index.ts` mirrors
`profile/__init__.py`'s export surface.

## Critique & Assessment

_Assessed 2026-08-21. The spec's two departures from ADR-0009 §8 were the main job; both are
accepted, and the ADR is amended rather than the approach._

### Necessity — justified
Decode cannot begin without the tables. No existing feature covers them: F18 produced the *Python*
tables, and this feature is about where the TypeScript ones come from. Nothing in the PRD's
non-goals is touched, and ADR-0004's hard constraint holds — no SDK material is committed, and the
departure below actually reduces how many people need the SDK at all.

### Placement — correct
`profile` is a leaf in both trees and imports nothing from the rest of `js/src`, matching Python
where `profile` and `errors` are the two leaves. Nothing here reaches upward.

### Departure 1 — transcode from the committed Python tables: **ACCEPTED**

ADR-0009 §8 specified a dual emitter reading the SDK. The spec's argument (no SDK for anyone but
the F18 maintainer; CI can regenerate from a clean checkout; drift becomes impossible to *commit*
rather than merely discouraged) holds. One argument the spec did not make is stronger than the ones
it did:

**`scripts/check_profile_against_fitdecode.py` is an independent oracle, and derivation makes it
cover both languages.** ADR-0004 §2 hard-gates the Python tables against fitdecode — a separately
authored MIT implementation — precisely because our tables' accuracy claims are load-bearing. Under
a dual emitter, that oracle would cover the Python table only, and the TypeScript table would need
its own. Under derivation, one oracle transitively covers both. Fewer oracles for the same
coverage is the right direction.

**The honest cost, which the spec understated: the profile is a shared-bug surface the corpus
cannot see.** If `generate_profile.py` mis-reads a scale, the Python table is wrong, the derived
TypeScript table is identically wrong, and `expected.json` was generated *from* the wrong Python —
so every corpus case passes while both implementations are wrong together. This is the exact
failure mode ADR-0001 §3 designed around when it made the corpus *tools* independent of chiptime.

It is worth stating plainly that derivation does not create this problem — ADR-0009 §8's dual
emitter shares it, since both emitters would parse the same SDK with the same code. The only design
that escapes it is Alternative 4 below, and it costs more than it buys. The mitigation is the
fitdecode oracle, and it should be named in the ADR as the thing standing between us and a
two-language shared bug, rather than left as an F18 implementation detail.

### Departure 2 — emit the merged tables: **ACCEPTED**

Porting the merge policy would create a second implementation of a rule with no test of its own,
whose divergence surfaces at F35 as a mysterious field-name difference. Emitting the merged result
keeps the policy in one language. The spec named the cost (provenance legibility) and mitigated it
with a header.

**What the spec missed is that the header it proposed would be wrong.** It said the emitted file
carries "the same provenance header `generated.py` carries (SDK version, ADR-0004 licensing
note…)". But the merged table is *not* the SDK profile — it is SDK breadth with hand-authored
overrides applied. Under ADR-0004, where the licensing position rests on these being *our* data
shapes with an accurate provenance trail, a header claiming pure SDK provenance for a file that is
partly hand-authored describes it wrongly in the one place it matters. Fixed by amendment B1.

### Approach — three further findings

**Finding 1 — `Map` was mandated where it buys nothing.** Requirement 12 applied F31's
"`Map` for ordered internals" rule to tables that are pure key lookups: nothing iterates them
order-sensitively, and the wrappers cost bundle bytes and load-time construction across ~5,000
entries. A principle applied without its reason is cargo cult. Narrowed by amendment B2, with the
no-order-reliance invariant stated in the emitted header so the next reader knows it is a decision
rather than an oversight.

**Finding 2 — float emission was assumed rather than specified**, and the profile contains
non-integral scales that make it load-bearing: `0.7111111`, `1.024`, `28.57143`, `10430.38`,
`11930464.711111112`. A scale off by one ULP silently mis-scales every value in its field — a
contract #1 violation with no provenance entry, produced by a *build script*. Amendment B4 pins
`repr` emission and principled string escaping (enum labels are mixed-case: `fenix6S`, `Edge_130`,
`india_zone_IIIA`).

**Finding 3 — no size budget, on a package that claims browser support.** `generated.py` is 232 KB
raw / 41 KB gzipped, and the TypeScript twin will be comparable. That is fine for a parsing library
and it is not fine to learn by accident, particularly since ADR-0009 §7 cited tree-shaking when
rejecting a runtime JSON asset — and a monolithic table is no more tree-shakeable than a JSON blob.
The honest position is that a complete profile is the product and its weight is the price; amendment
B3 requires measuring and reporting it rather than assuming.

**`check_profile_parity.py` is not tautological, and the distinction matters.** Requirement 15's
regenerate-and-diff catches *staleness* — it cannot catch a transcoder that has always been wrong
the same way. Requirement 14 loads the TypeScript values through `node` and compares them to the
Python values, which catches transcoding correctness: a truncated `bigint`, a float that lost a
digit, a mis-escaped label. Both gates are needed and they catch different things. Keep as
specified.

**Alternatives considered.**
1. *Dual emitter from the SDK (ADR-0009 §8 as written).* Rejected: requires the SDK for anyone
   regenerating either table, achieves drift-freedom only if both are always rerun together, and
   would need a second independent oracle to match the coverage derivation gets for free.
2. *Ship the profile as a JSON asset loaded at runtime.* Already rejected in ADR-0009 §7; with the
   new information the rejection is firmer — it adds a bundler-specific asset path and a parse at
   startup while saving nothing, since the bytes ship either way.
3. *Hand-port the tables.* 6,000 lines of transcription that guarantees divergence. Rejected.
4. *Generate the TypeScript tables independently from `Profile.xlsx`, in TypeScript.* The only
   design that makes the two profiles genuinely independent and would therefore catch a
   `generate_profile.py` bug. Rejected: it needs a zero-dependency xlsx reader in TypeScript, puts
   the SDK back in JS contributors' path, and buys independence that the fitdecode oracle already
   provides more cheaply. Logged to BACKLOG with its revisit trigger.

**At scale.** The tables are fixed-size regardless of input; hostile files cannot grow them.
Unknown-tolerance (contract #6) is what makes a stale table harmless, and it is the one behavior
this feature owns outright — tested here, corpus-covered at F33.

### Contract check
- **Silent loss** — the live risk is a *wrong* table silently mis-scaling values with no provenance
  entry, since a data table cannot emit one. Guarded by the fitdecode oracle upstream and by
  amendment B4 at the emission step.
- **Determinism** — sorted emission, no wall clock, `repr` floats. The emitted file is itself
  covered by regenerate-and-diff, so nondeterminism in the *generator* fails CI.
- **Sentinels & zero-vs-null** — Requirements 3/4 carry the sentinel semantics across exactly,
  including `bigint` for the 64-bit rows and the NaN treatment for floats. Zero-vs-null is a decode
  concern (F33); nothing here can blur it.
- **Modes** — correctly N/A and stated, not left blank.
- **Errors** — no new runtime failure paths; the emitter and parity checker are dev tooling.
- **Corpus** — correctly "none — data layer", with the taxonomy items attributed to F33 where
  snapshots become possible.

### Dependency analysis
No cycles. `js/src/profile` is a leaf. The new edge is build-time only: regenerating `generated.ts`
requires Python, which is acceptable because the artifact is committed — a JS-only contributor
never needs to regenerate unless the profile itself changes, and CI covers it when it does.

**Blast radius is total for decode and quiet.** A wrong table produces wrong field names and wrong
scales everywhere, and the F35 corpus gate would *not* catch it, because it compares TypeScript to
Python rather than either to reality. This is the strongest argument for keeping the fitdecode
oracle in the release path rather than treating it as an F18 artifact.

### Simplification — nothing cut
The candidates were examined and all kept. `check_profile_parity.py` earns its place (it catches
what regenerate-and-diff cannot). The vendor registry is 8 rows and belongs with its layer.
`core.ts` could fold into a neighbour, but module-for-module mirroring is a stated principle and
this is exactly where it costs nothing to honor. The only genuine over-specification was the `Map`
mandate, narrowed rather than dropped.

### Required follow-up: **ADR-0009 §8 must be amended**
The section describes a design this feature deliberately does not build. Rewrite it to specify
derivation from the committed Python tables, merged-table emission, the two CI gates, and — newly
— the fitdecode oracle as the mitigation for the shared-bug surface that neither design escapes.
`/implement` does this before writing code, so the ADR never describes something untrue.

### Final decision: **APPROVE** — with amendments B1–B4 applied above and the ADR-0009 §8 rewrite

Both departures are improvements on what the ADR specified, for reasons the ADR could not have
known before someone looked at `generated.py`. Three real findings fixed in the requirements, one
alternative logged, nothing cut.

## Dependencies
- **Depends on:** F31 (`js/` package, vectors harness pattern), F18 (the Python generated tables),
  F6 (vendor registry), ADR-0004, ADR-0009
- **Depended on by:** F33 (decode reads every table here), F34–F42

## Related
- ADR: [0004](../architecture/adrs/0004-profile-strategy.md), [0009](../architecture/adrs/0009-cross-language-parity.md)
- Plan: [../m3-typescript-plan.md](../m3-typescript-plan.md)
- Implementation: `../implementation/f32-js-profile-tables.md` (created by `/implement`)
