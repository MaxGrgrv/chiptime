# Feature: F7 — Semantic Model: Activity, Streams, Enhanced Pairs

> Status: DONE

## Purpose
Turn the lossless message layer into the canonical analytics-ready model: Activity → Sessions → Laps/Records with **columnar streams** where zero and null never blur (taxonomy #64), streams are independently sparse (#68), enhanced field pairs reconcile (#28), and developer fields promote to first-class streams via F6's registry.

## Context Check
- [x] All five context docs reviewed. F8 (timers/gaps) and F9 (reconciliation/rebuild/multisport) stack on this model.

## Taxonomy Coverage

| Taxonomy item # | Summary | Corpus case(s) |
|---|---|---|
| 64 | Zero vs null power distinction | clean/ride-smooth (streams now visible in snapshot) |
| 68 | Per-stream dropouts / validity | clean/ride-smooth (power absent records 50–55) |
| 28 | enhanced_speed/altitude pairs reconcile | semantics/enhanced-pairs |
| 50 (rule) | Lap end = start_time + elapsed, never write-timestamp | model invariant (Lap.end_time) |
| 23/24 | Unknown fields preserved | field_N record fields become streams — nothing dropped |

## Requirements
1. `model.py`: Activity / Session / Lap / Length / Totals / Records / Stream / DeviceInfo / AthleteProfile dataclasses per PRD §7.
2. `semantics/build.py`: two-pass, order-independent assembly (message order untrusted — contract #9). Sessions from session messages; records assigned by time containment (single-session tolerance; multisport refinement in F9); laps attached by time; `end_time = start_time + total_elapsed_time` (#50).
3. Streams: columnar, one per record field (native, `field_N` unknowns, developer). None = absent; 0 = zero. Sub-second alignment by record order. Sources tagged: `native` / `developer:<vendor>` / `developer`.
4. Enhanced pairs (#28): one `speed`/`altitude` stream, enhanced preferred per element; disagreement beyond scale rounding → warning + provenance (reinterpreted, counted). Never both silently.
5. Developer streams named by registry `canonical_name` when known, else description name.
6. Basic derived totals (elapsed, distance, null-aware avg/max per numeric stream); full reconciliation/discrepancies in F9.
7. Canonical JSON: parts gain `activity`; record-type messages leave `messages` (their content lives losslessly in streams — every field, known or not, becomes a stream).

## Acceptance Criteria
- [x] ride-smooth snapshot shows power stream with real 0s (coasting) and nulls (dropout) distinctly
- [x] enhanced-pairs case: single stream, enhanced values win, disagreement provenance present
- [x] Stryd case: `running_power` stream with source `developer:stryd`
- [x] summary-only activity: session with empty Records, no error

## Public API Impact
`ParseResult.activity` now populated (PRD §7 model). Canonical schema: `parts[].activity` added; record messages removed from `parts[].messages` when the model is built (documented; lossless via streams).

## Architectural Placement
semantics layer (`chiptime/model.py`, `chiptime/semantics/`).

## Proposed Approach
Per requirements; streams assembled from per-record field union in one pass over records.

## Critique & Assessment
- **Alternatives considered:** row-oriented records in JSON (rejected: 10× size, analytics-hostile — ADR-0002 spirit); keeping record messages AND streams in JSON (rejected: double weight; streams are lossless including unknown/dev fields).
- **Risks identified:** dropping record byte offsets from canonical output — accepted (forensics retain `iter_frames`; offsets are not activity data). Session containment edge cases pre-F9 — single-session tolerance documented.
- **Simplification opportunities:** moving_time/ascent/gaps deferred to F8/F9 where their policies live.
- **Contract check:** zero≠null structural in Stream.values; enhanced folding provenance'd; no silent drops (every record field streams); deterministic (means = sum/count on deterministic floats).
- **Final decision:** APPROVE

## Dependencies
- **Depends on:** F3, F6
- **Depended on by:** F8, F9, F10, F13

## Related
- Implementation: [../implementation/f07-semantic-model.md](../implementation/f07-semantic-model.md)
