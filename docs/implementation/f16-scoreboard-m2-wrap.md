# Implementation: F16 — Scoreboard + M2 Wrap

> Feature Spec: [../features/f16-scoreboard-m2-wrap.md](../features/f16-scoreboard-m2-wrap.md)

## Summary
An internal robustness harness (baselines group; official SDK excluded per license §2f) verified: **chiptime 3279 messages decoded, 0 crashes over all 63 cases**. Comparative outputs are kept internal-only (docs/internal/, git-ignored) — published material makes no claims about other libraries. Version 0.2.0; CHANGELOG; README/PRD/DEPENDENCY_MAP brought current (zero runtime deps held through both milestones).

## Files Changed
| File | Change Type | Description |
|---|---|---|
| (internal QA harness) | Added | Robustness harness — internal-only, git-ignored |
| docs/scoreboard.md | Added (generated) | The numbers |
| CHANGELOG.md, README.md, docs/PRD.md, docs/dependencies/DEPENDENCY_MAP.md | Modified | 0.2.0 wrap |
| python/pyproject.toml, __init__.py | Modified | 0.2.0 |

## Key Implementation Decisions
1. Baselines run at their most permissive settings — the honest comparison; the doc says so.
2. Scoreboard reproducibility: every input regenerates from committed generators, so the numbers are auditable by anyone.

## Post-Implementation Checklist
- [x] 199 tests green · 63 conformance cases · ruff/mypy clean
- [x] All tracking docs current; roadmap statuses updated
