# Feature: F13 — Repair Pipeline (`chiptime repair`)

> Status: DONE

## Purpose
The headline capability (research gaps #2/#3): parse with full salvage, synthesize whatever structure is missing (file_id, events, lap, session, activity), and emit a valid canonical `.fit` — with every synthesis in provenance and honest refusal when there is nothing to repair (#16).

## Taxonomy Coverage
| Taxonomy item # | Summary | Coverage |
|---|---|---|
| 95 → file | Rebuilt session emitted as a session MESSAGE | repair tests (truncated ride, Zwift crash class) |
| 96 | Missing activity/final-stop synthesized | repair tests |
| 102 | Minimum-viable-file structure for platforms | synthesis set + F14 validation |
| 16 | Empty file honesty: refuse to fabricate | REPAIR_NOTHING_TO_SALVAGE typed error |
| 2/9/10/19 (transitively) | Salvaged input → valid output file | truncated/corrupt inputs repair to strict-clean files |

## Requirements
1. `chiptime.repair(src) -> RepairResult(data, report, parse_result)`: lenient parse → primary activity part → structure completion → canonical encode (F12) → strict re-parse self-check (`output_strict_ok`).
2. Synthesis (only when absent, from the model's derived truth, provenance per action `REPAIR_*`): file_id (development manufacturer, time_created = first record), timer start/stop_all events, one covering lap, session message from derived totals, activity message. Absent derived values are omitted, never invented.
3. Canonical output order: file_id → file_creator → dev metadata → original message order → synthesized summaries (summary-last layout).
4. Honest refusal: no records AND no session ⇒ `NotRepairableError` (`REPAIR_NOTHING_TO_SALVAGE`) — data genuinely absent is reported, not fabricated (#16, contract #8).
5. CLI `chiptime repair IN -o OUT [--mode lenient|forensic]`: prints repair actions; exit 0 repaired / 3 unrepairable.

## Acceptance Criteria
- [x] Truncated ride repairs to a strict-clean file with session/lap/activity present
- [x] Zwift-crash class (records, no summaries) repairs; platform-required structure present
- [x] Empty/summary-less inputs refuse with the typed error
- [x] Repair output deterministic (same input → same bytes)

## Critique & Assessment
- **Alternatives considered:** patching original bytes in place (rejected: ADR-0006 canonical-form decision; unparseable regions make byte-patching quicksand); always synthesizing local_timestamp (rejected: unknown offset would be a fabrication — omitted instead, taxonomy #37 repair only *rewrites* local when UTC+offset are both known).
- **Risks identified:** platform folk-knowledge completeness → F14's explicit validation profiles carry that, marked heuristic.
- **Contract check:** every synthesized message → REPAIR_* provenance; refusal path honest; deterministic output.
- **Final decision:** APPROVE

## Dependencies
- **Depends on:** F9 (rebuild model), F12 · **Depended on by:** F14, F16

## Related
- Implementation: [../implementation/f13-repair-pipeline.md](../implementation/f13-repair-pipeline.md)
