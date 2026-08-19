# chiptime — Dependency Map

Cross-feature and module dependency tracking. Every "depends on" must have a matching "depended on by". Maintained by /update-deps.

## Feature Dependency Matrix

Compact form (full dependency sections live in each spec; every edge verified bidirectional 2026-08-18):

| Feature | Depends on | Depended on by |
|---|---|---|
| F1 scaffolding | — | all |
| F2 corpus+canonical | F1 | F3+ (all corpus-tested) |
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

## External Dependencies

**Runtime: none.** `python/pyproject.toml` has `dependencies = []` — adding one requires an ADR.

| Dependency (dev-only) | Group | Used by | Why |
|---|---|---|---|
| pytest, hypothesis | dev | tests | Test runner + property tests |
| mypy, ruff | dev | CI/verify | Types + lint/format |
| fitparse, fitdecode | baselines | scripts (QA) | Local QA oracles (profile cross-check, internal robustness harness); never imported by chiptime; no published comparisons |

## Update Log

| Date | Change |
|---|---|
| 2026-08-17 | Initial scaffold |
| 2026-08-17 | F1: dev/baselines dependency groups declared; runtime pinned at zero |
| 2026-08-18 | M1+M2 shipped: module layering recorded; runtime dependencies still ZERO |
| 2026-08-18 | M2.5 wrap: feature matrix filled (F1–F21); metrics module added (optional import only); pandas as optional extra — runtime core still ZERO |
