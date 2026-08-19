# Implementation: F19 — Real-File Corpus + PII Policy

> Feature Spec: [../features/f19-real-file-corpus.md](../features/f19-real-file-corpus.md)

## Summary
ADR-0007 implemented: git-ignored `corpus/private/` tier with its own manifest; `promote_real.py` promotion tool (`"build": "external"` — sha-verified, never regenerated); runner loads both tiers and skips absent private cases so public CI is untouched. **Six real files promoted**: the 9-resync damage survivor, a 3,463-record pool swim, the Wahoo ROAM ride, the 5-session IRONMAN (72,924 messages), the Zwift in-progress stub, and a Garmin-format activity. Real-ride investigation resolved the frozen-distance question: the ROAM's freezes are 3 short runs (max 12 s) at junction speeds — benign — so the detector now requires a ≥30-record consecutive run above 2 m/s (true dead-sensor signature); soak shows zero cycling false-positives with the synthetic dead-sensor case still firing.

## Also in this change: CI config-drift fix
The failed GitHub runs (F17/F18 pushes) were ruff resolving *different configs* for `scripts/` locally vs CI (files outside `python/` fell back to defaults depending on invocation directory). Root-level `ruff.toml` now governs the whole monorepo — local and CI cannot disagree by construction; redundant inline noqas removed; `[tool.ruff]` deleted from pyproject.

## Files Changed
| File | Change | Description |
|---|---|---|
| corpus/tools/promote_real.py | Added | Promotion tool (private tier) |
| corpus/tools/gen_all.py | Modified | `external` build handling + private glob |
| python/tests/conformance/test_corpus.py | Modified | Dual-manifest loading; `strict: unchecked` for real files |
| .gitignore | Modified | `corpus/private/` barred |
| python/src/chiptime/semantics/reconcile.py | Modified | DISTANCE_FROZEN → consecutive-run ≥30 @ >2 m/s |
| ruff.toml (+pyproject cleanup, noqa strips) | Added | Monorepo-wide lint config |
| docs/architecture/adrs/0007-real-file-pii-policy.md | Added | The policy |

## Key Decisions
1. Real files' strict-mode outcome is `unchecked` — device honesty varies; lenient/forensic grades + snapshots are the contract.
2. No public promotion in F19 (ADR-0007 §3): the pre-public-flip review owns that decision, file by file.
3. SDK sample files confirmed barred from both tiers.

## Post-Implementation Checklist
- [x] 210 tests green incl. 6 private conformance cases · ruff (both directions)/mypy clean
- [x] `git status` clean of real bytes; soak: 0 violations, DISTANCE_FROZEN false-positives 10 → 0
