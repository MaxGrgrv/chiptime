# Implementation: F13 — Repair Pipeline

> Feature Spec: [../features/f13-repair-pipeline.md](../features/f13-repair-pipeline.md)

## Summary
`chiptime.repair()` + `chiptime repair` CLI: lenient salvage → synthesis of missing file_id/events/lap/session/activity from the model's derived truth (only when absent; absent values omitted, never invented) → canonical re-encode → strict self-check. Honest refusal via `NotRepairableError(REPAIR_NOTHING_TO_SALVAGE)` when nothing survives (#16). Healthy files pass through with only `REPAIR_REENCODED` provenance.

## Files Changed
| File | Change Type | Description |
|------|------------|-------------|
| python/src/chiptime/repair.py | Added | Pipeline + synthesis + refusal |
| python/src/chiptime/cli.py | Modified | `repair` subcommand (exit 0 / 2 not-strict-valid / 3 unrepairable) |
| python/src/chiptime/__init__.py | Modified | `repair`, `RepairResult`, `NotRepairableError` exported |
| python/src/chiptime/errors.py | Modified | REPAIR_* provenance + refusal error code |
| python/tests/test_repair.py | Added | 8 tests: tail-clip, deep truncation, Zwift-crash class, healthy passthrough, refusal, determinism, CLI |

## Corpus Cases Added
None new — repair is exercised end-to-end in tests over existing corpus seeds (truncated ride, no_session); its outputs are validated by strict re-parse, the strongest available oracle. F14 adds platform-profile validation on top.

## Key Implementation Decisions
1. Synthesized summaries come from **derived** totals — the only truth available — and mark themselves via provenance; a repaired file's session is thereafter *declared* (that's the point: platforms need declarations).
2. `local_timestamp` is never synthesized (unknown offset would be fabrication — taxonomy #37 permits rewriting local only when UTC+offset are both known).
3. Healthy-file repair is a canonical re-encode only — `{REPAIR_REENCODED}` exactly, test-locked, so repair is safe to run unconditionally.
4. Deep-truncation test proves the full chain: resync salvage → model rebuild → session message synthesis → strict-valid output.

## Deviations from Spec
- None.

## Post-Implementation Checklist
- [x] Spec DONE · INDEX/OVERVIEW updated · 178 tests green · ruff/mypy clean (exit codes)
- [x] Every synthesis provenance'd; refusal honest; deterministic output
- [x] for-agents.md regenerated (REPAIR_* codes included)
