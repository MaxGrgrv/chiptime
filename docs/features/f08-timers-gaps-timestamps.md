# Feature: F8 — Timers, Gaps, Timestamp Policies

> Status: DONE

## Purpose
The temporal truth layer: a defensive timer state machine (#45), classified gaps instead of blind interpolation (#43/#44), explicit ordering policy (#41/#42), the three durations (#46), and absolute-time sanity flags (#37/#39/#40) — all per ADR-0005.

## Context Check
- [x] All five context docs reviewed; builds directly on F7's model.

## Taxonomy Coverage

| Taxonomy item # | Summary | Corpus case(s) |
|---|---|---|
| 43/44 | Gap classification incl. post-timer records | temporal/gap-classification |
| 45 | Timer machine, unbalanced events, missing final stop | temporal/gap-classification, temporal/missing-final-stop |
| 46 | Elapsed vs timer vs moving | temporal/gap-classification (derived totals in snapshot) |
| 41/42 | Non-monotonic sort + deterministic tie-break | temporal/non-monotonic-records |
| 37 | Zwift local_timestamp 1989 | temporal/zwift-local-timestamp-1989 |
| 39 | Pre-2010 timestamps flagged | temporal/pre-2010-timestamps |
| 40 | "Future" ≈ after file creation + 7d (ADR-0005 §2) | temporal/pre-2010-timestamps (creation drift variant) |
| 36 | FIT epoch correctness | implicit in every case since F3 |
| 47 | Local math never touches UTC stream | model invariant (utc_offset_s side-channel) |

## Requirements → ADR-0005 §1–§7 (normative). Additionally:
1. `Activity.utc_offset_s: int | None` exposed and serialized.
2. `Session.derived.timer_time_s` / `moving_time_s` populated; post-timer records excluded from both.
3. Gap objects on `Activity.gaps` with evidence strings naming the deciding events.
4. Corruption gaps: `_api` passes resynchronized byte ranges into the builder; a gap whose bounding records straddle a skipped range classifies as `corruption`.

## Acceptance Criteria
- [x] gap case: manual_stop (300 s, evidence names the events), smart_recording (25 s), unknown (45 s), post_timer trailing records — all classified in one file
- [x] non-monotonic case: sorted timeline, RECORDS_REORDERED provenance, duplicate second kept stable
- [x] Zwift case: utc_offset_s null + LOCAL_TIMESTAMP_IMPLAUSIBLE; healthy files get the right offset (ride_smooth: +7200)

## Public API Impact
`Activity.utc_offset_s`, `Activity.gaps` populated, `Gap` in canonical JSON. New warning/provenance codes per ADR-0005.

## Architectural Placement
semantics layer: `semantics/timers.py`, `semantics/gaps.py`, build.py integration.

## Proposed Approach
Sort → assign → timers → streams → derive → gaps, single pass each.

## Critique & Assessment
- **Alternatives considered:** dropping out-of-order records (rejected: silent loss; FFRT's auto-remove is exactly what we refuse); wall-clock future detection (rejected: determinism contract; ADR-0005 §2 approximation instead); interpolating gaps (rejected: taxonomy #43 "never blindly interpolate").
- **Risks identified:** moving-time heuristic (speed>0.1, dt cap 30 s) is opinionated → documented in ADR + honestly None without a speed stream; timer_trigger read from event.data raw (subfield resolution proper lands F15) — works for the timer case, noted.
- **Simplification opportunities:** DST/timezone-crossing depth (#47 full) deferred to BACKLOG (needs real-world multi-zone fixtures).
- **Contract check:** reorder/synthesis → provenance; flags are warnings with stable codes; no wall clock anywhere; UTC stream immutable.
- **Final decision:** APPROVE

## Dependencies
- **Depends on:** F5 (skip ranges), F7
- **Depended on by:** F9 (reconciliation uses timer/moving), F13 (repair)

## Related
- ADR: [0005](../architecture/adrs/0005-timestamp-policies.md)
- Implementation: [../implementation/f08-timers-gaps-timestamps.md](../implementation/f08-timers-gaps-timestamps.md)
