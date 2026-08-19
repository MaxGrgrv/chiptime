# Feature: F11 — CLI, Agent Docs, M1 Wrap (0.1.0)

> Status: DONE

## Purpose
Ship it: the command-line surface with agent exit codes, generated for-agents documentation, hardening gates (cross-process determinism, truncation sweep), CI workflow, CHANGELOG, version 0.1.0, and the Tier-1 completeness audit.

## Taxonomy Coverage
| Taxonomy item # | Summary | Corpus case(s) |
|---|---|---|
| 50 | Summary-first layout (Dec-2023 change) | temporal/summary-first-layout (closed the last Tier-1 gap) |

## Requirements
1. `chiptime parse|inspect|codes` CLI: summary + canonical-JSON output, wire-level frame table, code registry dump; exit codes 0/2/3/4/64 as a stable contract; `python -m chiptime` works.
2. `docs/for-agents.md` generated from the code registries (`scripts/gen_agent_docs.py`) — codes can never drift from docs.
3. Hardening gates as tests: cross-process canonical byte-identity; truncate-at-every-offset sweep (lenient never raises, always serializes; strict only ever raises typed FitErrors).
4. `.github/workflows/ci.yml`: ubuntu+macos × 3.11+3.13, lint/types/corpus-integrity/tests.
5. CHANGELOG.md; version 0.1.0; Tier-1 audit green.

## Acceptance Criteria
- [x] All 18 Tier-1 items corpus-covered (audit: 18/18, 56 cases, 54 distinct taxonomy items)
- [x] 157 tests green; every gate checked by exit code (lesson from F10 encoded in /verify)
- [x] `chiptime parse broken.fit` exit 2 with provenance in summary

## Public API Impact
CLI surface + exit-code contract; `chiptime.__main__`. Version 0.1.0.

## Critique & Assessment
- **Alternatives considered:** click/typer for the CLI (rejected: zero-dep contract); hand-written for-agents.md (rejected: registries already exist in code — generation kills drift).
- **Risks identified:** exit-code conflation of "recovered" vs "warnings-only" — resolved: warnings-only is 0, recovery/data-loss is 2.
- **Contract check:** JSON output is exactly `to_canonical_json()` bytes; summary prints every provenance/warning/error line — nothing hidden.
- **Final decision:** APPROVE

## Dependencies
- **Depends on:** F1–F10 · **Depended on by:** M2 features (repair CLI extends this surface)

## Related
- Implementation: [../implementation/f11-cli-agent-docs-m1-wrap.md](../implementation/f11-cli-agent-docs-m1-wrap.md)
