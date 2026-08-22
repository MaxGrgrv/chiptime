# Implementation: F45 — Timer redundant-stop fix

> Feature Spec: [docs/features/f45-timer-redundant-stop.md](../features/f45-timer-redundant-stop.md)

## Summary

Narrowed the timer state machine's two salvage heuristics (ADR-0005 §5, taxonomy #45) so
they fire only for the genuine crash classes they were written for. A stop-kind event with
no interval open is now a no-op (provenance `TIMER_REDUNDANT_STOP`) when intervals already
exist or when the would-be anchor is not strictly before the stop — killing the phantom
whole-activity interval a Wahoo ELEMNT ROAM shutdown produced (derived timer 37658 s vs
the correct 18828 s on the discovering race file) and the spurious
`TIMER_STOP_WITHOUT_START` warning Suunto multisport boundary slicing produced. The
missing-final-stop synthesis is likewise gated on actually appending a non-empty interval;
a dangling boundary-leaked start is a no-op (provenance `TIMER_REDUNDANT_START`).
Mirrored in the TypeScript twin; three new corpus cases; zero changes to existing
expected outputs.

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `python/src/chiptime/semantics/timers.py` | Modified | Redundant-stop no-op branch; synthesis gated on non-empty close; `TIMER_REDUNDANT_START` branch |
| `js/src/semantics/timers.ts` | Modified | Exact mirror of the Python branches |
| `python/src/chiptime/errors.py` | Modified | `TIMER_REDUNDANT_STOP` + `TIMER_REDUNDANT_START` in `PROVENANCE_CODES` |
| `js/src/codes.ts` | Regenerated | via `scripts/gen_codes_ts.py` (38 provenance codes) |
| `docs/for-agents.md` | Regenerated | via `scripts/gen_agent_docs.py` |
| `website/reference/codes/*` | Regenerated | via `scripts/gen_code_pages.py` (110 pages + index) |
| `corpus/tools/build_fit.py` | Modified | Seeds `wahoo_shutdown`, `multisport_timer_events`, `stop_without_start` |
| `corpus/MANIFEST.json` | Regenerated | 72 → 75 cases |
| `python/tests/test_temporal.py` | Modified | Three unit tests pinning the new branches |
| `docs/architecture/adrs/0005-timestamp-policies.md` | Modified | §5 narrowed-heuristic wording |
| `docs/edge-case-taxonomy.md` | Modified | #45 line: redundant shutdown stops, boundary leaks |

## Corpus Cases Added

| Case | Taxonomy item # | How generated |
|------|-----------------|---------------|
| `corpus/cases/temporal/redundant-stop-shutdown/` | #45 | synthetic seed `wahoo_shutdown` (start/stop/start/stop + same-second `stop_all` + session `stop_disable_all`; session declares the correct 65 s timer — snapshot proves `discrepancies: []`) |
| `corpus/cases/multisport/boundary-timer-events/` | #45, #75 | synthetic seed `multisport_timer_events` (two sessions sharing a boundary second, per-session start/`stop_all` pairs + session `stop_disable_all` events) |
| `corpus/cases/temporal/stop-without-start/` | #45 | synthetic seed `stop_without_start` (records precede the first stop — the genuine crash class keeps its warning; previously this branch had no corpus coverage at all) |

## Key Implementation Decisions

1. **Degenerate anchors decide, not event kinds.** The no-op conditions are structural
   (`intervals` non-empty, or anchor not strictly before the stop; close would append
   nothing) rather than pattern-matching on `stop` vs `stop_all` vs vendor — so any
   device's redundant-event shape is covered, and the genuine crash classes (which always
   carry real records on the salvageable side of the event) are untouched.
2. **Ignored events get provenance, not silence.** Contract #1: the machine's decision to
   ignore a timer event when reconstructing intervals is recorded (`action: "ignored"`),
   while the events themselves remain losslessly in `events[]`/messages. Static detail
   strings keep determinism.
3. **Session-scoped `stop_disable_all` events stay excluded** by the existing
   `event == "timer"` filter; both new seeds include them to pin that invariant in the
   snapshots.
4. **The Wahoo-pattern seed declares the device's correct 65 s timer** so its snapshot
   proves the end-to-end symptom is gone: `declared == derived`, `discrepancies: []`.

## Deviations from Spec

- **Amendment E1** (recorded in the spec): the boundary leak is symmetric, and the
  planned snapshot exposed a second false claim — a dangling leaked *start* still emitted
  `TIMER_STOP_SYNTHESIZED` while appending nothing (or a zero-length interval when the
  boundary record is shared). Synthesis is now gated on a non-empty close; the degenerate
  dangling start emits `TIMER_REDUNDANT_START` instead. Consequence: a start-only file
  with no records now derives `timer_time_s = None` (honest) rather than `0.0` via a
  zero-length interval; no committed case or observed real file depended on the old value.

## Lessons Learned

- The corpus-first discipline caught E1 before it shipped: reviewing the snapshot as an
  executable spec surfaced a false provenance claim that code review of the diff alone
  would have missed (the `TIMER_STOP_SYNTHESIZED` path wasn't in the diff).
- Salvage heuristics need their *negative* cases in the corpus. `TIMER_STOP_WITHOUT_START`
  had shipped in F8 with no corpus case exercising it — which is exactly how its misfire
  on legal device patterns went unnoticed until a real race file.

## Post-Implementation Checklist
- [x] Feature spec status updated to DONE
- [x] INDEX.md updated
- [x] DEPENDENCY_MAP.md updated
- [x] Architecture docs updated (if needed) — ADR-0005 §5; OVERVIEW unchanged (no new modules)
- [x] All new behavior covered by corpus cases and/or unit tests
- [x] Every new drop/repair/reinterpretation emits provenance
- [x] Determinism verified (same input → byte-identical canonical output)
- [x] Skills assessed and updated (if needed) — none needed
