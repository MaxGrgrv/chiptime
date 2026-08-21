# chiptime — Dependency Map

Cross-feature and module dependency tracking. Every "depends on" must have a matching "depended on by". Maintained by /update-deps.

## Feature Dependency Matrix

Compact form (full dependency sections live in each spec; every edge verified bidirectional 2026-08-18):

| Feature | Depends on | Depended on by |
|---|---|---|
| F1 scaffolding | — | all (incl. F31, which mirrors its repo/CI conventions in `js/`) |
| F2 corpus+canonical | F1 | F3+ (all corpus-tested), F31 (`canonical.py` is the port's reference) |
| F3 decode core | F1, F2 | F4–F21 |
| F4 intake | F3 | F5, F13 |
| F5 recovery/resync | F3, F4 | F10, F13, F15, F17 |
| F6 dev fields | F3 | F7, F12 |
| F7 semantic model | F3, F6 | F8–F10, F13, F21 |
| F8 timers/gaps | F5, F7 | F9, F13, F14, F21(zones dt policy) |
| F9 reconcile/rebuild | F7, F8 | F13, F14, F15, F17 |
| F10 gps plausibility | F7 | F13, F15(pattern), F20(prefilter) |
| F11 cli/M1 wrap | F1–F10 | F13, F14 (CLI verbs) |
| F12 encoder | F3, F6 | F13, F14, F16 |
| F13 repair | F9, F12 | F14, F16, F17 |
| F14 validation | F13 | F16, F17 |
| F15 tier-2 depth | F7–F10 | F16, F21(swim) |
| F16 robustness gate/M2 wrap | F1–F15 | — |
| F17 soak fixes | F9, F13, F15 | F19 |
| F18 profile generation | F3 (ADR-0004) | F19, F21 |
| F19 real-file corpus | F17, F18 | F21(real SWOLF), M3 |
| F20 performance | F3, F7, F10 | — (BACKLOG: columnar decode → M3) |
| F21 hrv/metrics | F7, F8, F15, F19 | F23 (basics re-exported) |
| F23 sport profiles/pacing | F7 (model), F21 (ADR-0008) | F24 (profiles+signal), F25 (pacing+zones) |
| F24 interval detection | F23, F7 (model/laps/lengths) | F25 (report embeds structure) |
| F25 insights/load/analyze | F23, F24, F11 (CLI), F21 (basics) | — |
| F26 edit (metadata) | F3 (decode), F12 (encoder), F13 (repair pattern), F11 (CLI) | F27/F28/F30 (share the transform+re-encode skeleton), M3 |
| F27 trim (crop) | F3, F7/F9 (build_activity, derived totals), F12, F13 (`_summary_message`), F11 | F30 |
| F28 privacy (reveal/scrub) | F3, F12, F11, ADR-0007 | M3 (TS twin), client-side browser tool |
| F29 doctor + calibration | F13 repair, F14 validate, F26 edit, F11 CLI | — (composition layer) |
| F31 js scaffolding/canonical/numeric (M3) | F1, F2 (`canonical.py` is the reference), ADR-0002, ADR-0009 | F32–F42 (every TypeScript module) |
| F32 js profile tables (M3) | F31, F18 (the merged Python tables it transcodes), F6 (vendor registry), ADR-0004, ADR-0009 | F33+ (decode reads every table) |
| F33 js errors/message/frames (M3) | F31, F32, F3 (frame half, as reference), ADR-0003, ADR-0009 | F34+ (the decoder and everything above it) |
| F34 js decoder (M3) | F31 (numeric), F32 (profile), F33 (frames/errors/message), F3/F6/F22 as reference | F35+ (parse, semantics, everything above) |
| F35 js intake/inflate/parse/result (M3) | F31–F34, F4/F5/F11/F15 as reference, ADR-0002 | F36+ (semantics fills the activity block) |

## Module Dependencies

Strictly downward (verified by import inspection, 2026-08-18):

```
cli ─→ _api, repair, validate, errors, frames
validate ─→ _api (parse)
repair ─→ _api, encode, model, errors
encode ─→ frames(crc16), message, profile, decode(epoch)
_api ─→ intake, frames, decode, semantics, result, errors
semantics.build ─→ decode(epoch), model, message, errors, semantics.{timers,gaps,reconcile,plausibility}
decode ─→ frames, message, profile, errors
intake, frames ─→ errors (leaf), profile.base_types
result ─→ canonical, errors, message
profile, canonical, errors, model, message ─→ (leaves)
```

No cycles; `decode` never imports `semantics`; `profile` and `errors` remain leaves.

### TypeScript (`js/src`) — as built at F31

```
index ─→ canonical
canonical ─→ (leaf — imports nothing, not even numeric: formatting is String(x), not rounding)
numeric ─→ (leaf; INTERNAL — absent from the exports map, no Python analogue)
api ─→ intake, frames, decode, result, errors, numeric, sha256
intake ─→ inflate, errors
result ─→ canonical, errors, message
inflate, sha256 ─→ (leaves; no Python twin)
decode ─→ frames, message, profile, errors, numeric  (never semantics)
frames ─→ errors, profile/base-types
errors ─→ codes (generated)
message ─→ frames (types only)
profile/index ─→ profile/{base-types, core, generated, registry}
profile/generated ─→ profile/core (types only)
profile/{base-types, core, registry} ─→ (leaves)
```

`js/src/profile` imports nothing from the rest of `js/src`, matching Python where `profile` and
`errors` are the two leaves. `profile/generated.ts` is transcoded from the Python package by
`scripts/gen_profile_ts.py` — a **build-time** edge only (the artifact is committed), gated in CI
by regenerate-and-diff plus `scripts/check_profile_parity.py`.

The tree mirrors `python/src/chiptime/` module-for-module (ADR-0009), with `numeric.ts` as the one
deliberate exception: Python uses the stdlib where TypeScript needs an explicit kernel. No `node:`
import executes at module load anywhere in `js/src` — enforced by `js/scripts/smoke.sh`.

## External Dependencies

**Runtime: none, in both languages.** `python/pyproject.toml` has `dependencies = []`;
`js/package.json` has `"dependencies": {}`. Adding one on either side requires an ADR
(ADR-0009 §7 is why the JS side ships its own inflate rather than reaching for `node:zlib`).

| Dependency (dev-only) | Group | Used by | Why |
|---|---|---|---|
| pytest, hypothesis | dev | tests | Test runner + property tests |
| mypy, ruff | dev | CI/verify | Types + lint/format |
| fitparse, fitdecode | baselines | scripts (QA) | Local QA oracles (profile cross-check, internal robustness harness); never imported by chiptime; no published comparisons |
| typescript | js dev | `js/` build + typecheck | Two plain `tsc` passes (ESM, CJS); no bundler on the publish path |
| vitest | js dev | `js/test` | Test runner; the conformance runner lands on it at F33 |
| @biomejs/biome | js dev | CI/verify | Lint + format — the `ruff` analogue |
| @types/node | js dev | `js/test`, `js/scripts` | Test and tooling only; `js/src` compiles with `lib: ["ES2022"]` and no node types |

## Update Log

| Date | Change |
|---|---|
| 2026-08-17 | Initial scaffold |
| 2026-08-17 | F1: dev/baselines dependency groups declared; runtime pinned at zero |
| 2026-08-18 | M1+M2 shipped: module layering recorded; runtime dependencies still ZERO |
| 2026-08-18 | M2.5 wrap: feature matrix filled (F1–F21); metrics module added (optional import only); pandas as optional extra — runtime core still ZERO |
| 2026-08-21 | F35 (M3): `intake`/`inflate`/`sha256`/`result` added; `api` gains `parse()`. `inflate` and `sha256` are the only modules with no Python counterpart — forced by zero-deps + sync + browser. Runtime dependencies still ZERO |
| 2026-08-21 | F34 (M3): `decode.ts` added above frames/profile/errors/numeric; `api` gains `iterMessages`. Runtime dependencies still ZERO |
| 2026-08-21 | F33 (M3): `errors`/`codes`/`message`/`frames`/`api` added; `errors` is a leaf over the generated `codes.ts`; `frames` imports only `errors` and `profile/base-types`, matching Python. Runtime dependencies still ZERO |
| 2026-08-21 | F32 (M3): `js/src/profile` added as a leaf; new build-time edge js-profile ← python-profile (committed artifact, two CI gates). Runtime dependencies still ZERO in both languages |
| 2026-08-21 | F31 (M3): `js/` package added with its own dependency table. Runtime dependencies ZERO in both languages; JS dev group is typescript/vitest/biome/@types/node. TypeScript module tree recorded; `canonical.ts` and `numeric.ts` are both leaves |
