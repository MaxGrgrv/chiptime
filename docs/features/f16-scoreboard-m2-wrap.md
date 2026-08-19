# Feature: F16 — Recovery Scoreboard + M2 Wrap (0.2.0)

> Status: DONE

## Purpose
Ship M2 with a measurable robustness gate: an internal QA harness over the whole corpus, version 0.2.0, docs closure.

## Taxonomy Coverage
None new — this measures everything prior.

## Requirements
1. An internal robustness harness (baselines group) runs reference parsers locally as QA oracles over all corpus cases. Results stay internal — published material makes no comparative claims; the official SDK is never run (license §2f).
2. Version 0.2.0, CHANGELOG, README refresh, PRD roadmap status, dependency-map update log.

## Acceptance Criteria
- [x] Robustness gate green: chiptime decodes every corpus case with zero crashes (3279 messages across 63 cases)
- [x] All docs current; 199 tests green

## Critique & Assessment
- **Risks identified:** scoreboard could be read as unfair (corpus is ours) → the doc states the corpus composition and that baselines run at best-case settings; every case is reproducible from committed generators.
- **Final decision:** APPROVE

## Related
- Implementation: [../implementation/f16-scoreboard-m2-wrap.md](../implementation/f16-scoreboard-m2-wrap.md)
