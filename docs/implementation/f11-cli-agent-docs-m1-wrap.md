# Implementation: F11 — CLI, Agent Docs, M1 Wrap

> Feature Spec: [../features/f11-cli-agent-docs-m1-wrap.md](../features/f11-cli-agent-docs-m1-wrap.md)

## Summary
M1 shipped as 0.1.0. `cli.py` (parse/inspect/codes; exit contract 0/2/3/4/64; usage errors 64 via ArgumentParser subclass), `__main__.py`, generated `docs/for-agents.md`, hardening tests (cross-process determinism via subprocess; full truncation sweep in both lenient and strict), CI workflow (2 OS × 2 Python + corpus sha-guard job), CHANGELOG, summary-first corpus case closing Tier-1.

## Files Changed
| File | Change Type | Description |
|------|------------|-------------|
| python/src/chiptime/cli.py, __main__.py | Added | CLI + module entry |
| python/tests/test_cli.py | Added | 11 tests: exit codes, JSON, inspect, codes, -m entry |
| python/tests/test_hardening.py | Added | Determinism + truncation sweeps |
| scripts/gen_agent_docs.py → docs/for-agents.md | Added | Registry-driven agent documentation |
| .github/workflows/ci.yml | Added | Matrix CI |
| CHANGELOG.md | Added | 0.1.0 notes |
| corpus/tools/build_fit.py | Modified | summary_first seed (#50) |
| python/pyproject.toml, __init__.py | Modified | 0.1.0 |

## Corpus Cases Added
temporal/summary-first-layout (#50). Final M1 census: **56 cases, 54 distinct taxonomy items, Tier-1 18/18.**

## Key Implementation Decisions
1. Exit code 2 means "you got data, something was lost/repaired — read provenance"; warnings alone stay 0 (agents shouldn't branch on cosmetics).
2. for-agents.md is generated, never edited — the registries in `errors.py` are the single source of truth.
3. The strict-mode truncation sweep asserts the *error contract* (only typed FitErrors), not specific codes — cut-point-specific codes are corpus business.

## Lessons Learned
`set -o pipefail` / per-command exit checks are now standing verification practice (F10's masked-mypy incident; /verify updated).

## Post-Implementation Checklist
- [x] Spec DONE · INDEX updated · 157 tests green (56 conformance) · ruff/mypy/format clean, exit codes checked
- [x] Tier-1 audit: 18/18 · CHANGELOG · version 0.1.0
- [x] Skills updated (/verify exit-code rule)
