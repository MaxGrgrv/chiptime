# Feature: F45 — Timer redundant-stop fix (Wahoo shutdown / Suunto boundary patterns)

> Status: DONE

## Purpose

A real Wahoo ELEMNT ROAM race file (5 h 13 m ride) exposed a misfire in the timer state
machine's stop-without-start heuristic (ADR-0005 §5, taxonomy #45). The device's standard
shutdown writes a redundant `stop_all` at the same timestamp as the final `stop`:

```
timer start @06:41:30 · stop @11:55:13 (data=1) · start @11:55:15
timer stop @11:55:20 (data=0) · stop_all @11:55:20 · session stop_disable_all @11:55:20
```

When the trailing `stop_all` arrives with no interval open, `build_timer_state()` treats it
as a crash-class "stop without start" and opens a phantom interval at the **first record** —
spanning the whole activity. Observed damage: `derived.timer_time_s` = 18823 + 5 + 18830
(phantom) = 37658 vs the device's correct 18828 → a false `timer_time_s` discrepancy plus a
spurious `TIMER_STOP_WITHOUT_START` warning. Because gap classification consults the same
intervals, stopped-time gaps inside the phantom span are also misclassified as running time.

A second shape, confirmed by synthetic reproduction (and matching the Venice Suunto
multisport file): with per-session event slicing (`_session_events`, F9), session N+1's
window `[start, end]` includes session N's boundary `stop_all` written at the same second as
session N+1's `start`. The leading stop arrives with no interval open and no intervals built,
opens a zero-length phantom at session N+1's first record — timers stay numerically correct,
but the spurious `TIMER_STOP_WITHOUT_START` warning fires per boundary.

Both shapes are legal device behavior, not crash damage. The heuristic must fire only for the
genuine crash class it was written for.

## Context Check
- [x] Reviewed docs/INDEX.md for existing features
- [x] Reviewed docs/architecture/OVERVIEW.md for architectural fit
- [x] Reviewed docs/dependencies/DEPENDENCY_MAP.md for conflicts
- [x] Reviewed docs/PRD.md for scope and principles alignment
- [x] Reviewed docs/edge-case-taxonomy.md for related edge cases
- [x] No duplication with existing features (F8 built the machine; this corrects one branch)

## Taxonomy Coverage

| Taxonomy item # | Summary | Corpus case(s) planned |
|---|---|---|
| 45 | Timer event stack: unbalanced events, `stop_all` without start, redundant shutdown stops | `corpus/cases/temporal/redundant-stop-shutdown/` (Wahoo pattern), `corpus/cases/temporal/stop-without-start/` (genuine crash class — previously untested branch) |
| 45 + 75 | Per-session timer events across multisport boundaries | `corpus/cases/multisport/boundary-timer-events/` (Suunto pattern) |

## Requirements

1. **Redundant stop is a no-op.** A stop-kind event (`stop`/`stop_all`/`stop_disable_all`)
   arriving with `open_start = None` when intervals have already been built must not open an
   interval and must not warn. It is recorded as provenance `TIMER_REDUNDANT_STOP`
   (action `ignored`) — quiet, honest, per contract #1.
2. **Degenerate anchor is a no-op.** When no intervals exist yet and the would-be anchor
   (first record, else the stop time itself) is **not strictly before** the stop time, the
   opened interval would be zero-length or inverted and salvages nothing. Same treatment:
   no interval, no warning, provenance `TIMER_REDUNDANT_STOP`. This quiets the multisport
   boundary-leak shape without touching `_session_events` slicing.
3. **The genuine crash class keeps its behavior.** No intervals yet + first record strictly
   before the stop → open at the first record, warn `TIMER_STOP_WITHOUT_START`, set
   `stop_without_start` — byte-identical to today for true file-begins-with-stop damage.
4. **New provenance code registered once, propagated everywhere**: `PROVENANCE_CODES` in
   `python/src/chiptime/errors.py`, then generated surfaces (`js/src/codes.ts` via
   `gen_codes_ts.py`, `docs/for-agents.md` via `gen_agent_docs.py`, website code pages via
   `gen_code_pages.py`).
5. **TypeScript twin mirrors exactly** (`js/src/semantics/timers.ts`, F36): same branch
   order, same detail strings, byte-identical canonical JSON on all corpus cases.
6. **ADR-0005 §5 updated** to state the narrowed heuristic; taxonomy #45 line notes the
   redundant-shutdown-stop pattern.
7. **No existing expected.json changes.** No committed case exercises the misfiring branch
   (verified: no `TIMER_STOP_WITHOUT_START` appears in any expected.json). The full corpus
   must stay green in both languages without regeneration; the three new cases add coverage.

## Acceptance Criteria
- [x] Wahoo-pattern repro: derived timer = sum of real intervals (65 s in the synthetic
      case), no `TIMER_STOP_WITHOUT_START`, one `TIMER_REDUNDANT_STOP` provenance entry
- [x] Suunto-pattern repro: per-session timers correct (100 s / 200 s synthetic), no
      `TIMER_STOP_WITHOUT_START`, one `TIMER_REDUNDANT_STOP` per later-session boundary
      (plus one `TIMER_REDUNDANT_START` per earlier-session boundary — amendment E1)
- [x] Genuine crash case: warning + interval opened at first record, unchanged
- [x] Every taxonomy item above has at least one corpus case with committed expected output
- [x] All three new cases byte-identical between Python and TypeScript runners
- [x] Full existing corpus green in both languages with zero expected.json diffs
      (`check_parse_parity.py`: 75 cases, 225 case/mode combinations agree)
- [x] Behavior identical across strict / lenient / forensic (timer machine is mode-blind;
      cases record `ok` for all three modes)

## Public API Impact

- New provenance codes `TIMER_REDUNDANT_STOP` and `TIMER_REDUNDANT_START` (amendment E1,
  below) — additive; no schema version change (provenance codes are an open set per
  `for-agents.md`).
- Behavioral: `TIMER_STOP_WITHOUT_START` no longer emitted for redundant/degenerate stops
  (it was wrong there); still emitted for the genuine crash class.
  `TIMER_STOP_SYNTHESIZED` no longer emitted when the synthesized close would append
  nothing (E1) — it claimed a synthesis that never happened.
- No signature changes in either language.

### Amendment E1 (discovered during implementation)

The multisport boundary leak is symmetric. Reviewing the new
`multisport/boundary-timer-events` snapshot before committing it showed session N's window
also catches session N+1's boundary **start** (same shared second), leaving a dangling
open interval whose close appends nothing (the last record is at or before the leaked
start) — yet `TIMER_STOP_SYNTHESIZED` still fired, claiming "no final timer stop event"
for a session that had one. Committing that snapshot would have baked the false claim into
the cross-language contract. Fix, mirrored in both languages: synthesize (interval +
provenance) only when the close appends a non-empty interval; a degenerate dangling start
is a no-op recorded as provenance `TIMER_REDUNDANT_START` (action `ignored`). The genuine
crash class (start with records after it) synthesizes exactly as before.

## Architectural Placement

`semantics` layer only: `python/src/chiptime/semantics/timers.py` and
`js/src/semantics/timers.ts` (`build_timer_state` / `buildTimerState`). Registry in
`errors` leaf + generated docs. Corpus tooling: three new seed builders in
`corpus/tools/build_fit.py` + `SEEDS` entries. No changes to `build.py` event slicing.

## Proposed Approach

In the stop branch of the event loop, replace the unconditional heuristic with:

```
if open_start is None:
    anchor = first_record if first_record is not None else t
    if intervals or anchor >= t:
        provenance += TIMER_REDUNDANT_STOP (action "ignored"); continue
    stop_without_start = True; warn TIMER_STOP_WITHOUT_START; open_start = anchor
append (open_start, t) if open_start <= t; open_start = None
```

Provenance detail (shared string, both languages):
`"timer stop event with no interval open ignored as redundant"`.

Corpus seeds (deterministic, `FitBuilder`):
- `wahoo_shutdown()` — single session; start/stop(data=1)/start/stop(data=0)/`stop_all`
  same-second + session-scoped `stop_disable_all` event (already filtered by
  `event == "timer"`; present to pin that invariant).
- `multisport_timer_events()` — two sessions sharing a boundary second; per-session
  start/`stop_all` pairs + session `stop_disable_all` events (Venice pattern).
- `stop_without_start()` — records from t0, first timer event is a `stop` at t0+30, then
  start/stop pair: the genuine crash class keeps its warning.

## Critique & Assessment

- **Necessity:** Confirmed by two independent reproductions (both synthetic repros built
  from the real files' event streams misfire on current code: 132 s vs 65 s timer in the
  Wahoo shape; spurious warning in the Suunto shape). The bug corrupts `timer_time_s`,
  moving time, gap classification, and reconciliation discrepancies — core M1 semantics.
  Not covered by any existing feature; F8 built the branch, this narrows it.
- **Alternatives considered:**
  1. *Condition only on `intervals` non-empty* (the minimal fix): repairs the Wahoo shape
     but leaves the Suunto multisport boundary warning firing — rejected; the Venice
     evidence is real and the degenerate-anchor rule is two lines.
  2. *Fix at the slicing level* (`_session_events` half-open windows or boundary dedupe):
     rejected — session N's final stop and session N+1's start legitimately share a second,
     so no window rule separates them without breaking one side; slicing also feeds gap
     classification, widening the blast radius; and the timer machine should be defensive
     against leading stops regardless of who produced them (defensive-by-design, #45).
  3. *Dedupe same-timestamp consecutive stops in preprocessing*: rejected — narrower (a
     later `stop_all` at a different second is equally redundant) and misses the boundary
     shape entirely.
- **Risks identified:** (a) The no-record + lone-stop pathology changes output: previously
  a zero-length interval made `timer_time_s` 0.0 with a warning; now honestly `None` with a
  quiet note — no corpus case or real file observed depends on the old value, and `None` is
  the honest answer (contract #8). (b) A leaked boundary stop with records strictly before
  it (records attached outside session bounds) still takes the genuine-crash branch — the
  machine cannot distinguish that from a real crash; accepted, warning is defensible there.
  (c) Behavior change is warning-level only for shapes proven wrong; the genuine branch is
  byte-identical, pinned by the new `stop-without-start` case.
- **Simplification opportunities:** This is already the 20% version — two conditions in one
  branch, no new state, no slicing changes. Nothing to cut without losing one of the two
  proven shapes. Real-file promotion and a slicing audit deferred to BACKLOG.
- **Contract check (silent loss / determinism / provenance / sentinels):** No data loss —
  ignored events remain losslessly in `events[]`/messages; the ignore action is recorded as
  provenance (contract #1). Static detail strings, file-ordered entries — deterministic.
  Sentinels untouched. Mode-blind (documented); new code registered with human sentence and
  propagated to all generated surfaces.
- **Dependency analysis:** No new imports, no cycles; semantics-layer only. Blast radius:
  session totals (timer/moving), gaps, reconcile — exactly the surfaces the corpus pins;
  requirement 7 (zero expected.json diffs) is the regression guard, enforced in both
  languages by the parity gates (ADR-0009).
- **Final decision:** **APPROVE** — proceed to /implement as specified.

## Dependencies
- **Depends on:** F8 (timer machine), F9 (`_session_events` multisport slicing — interplay
  only, unchanged), F36 (TS twin), F2 (corpus infra), corpus tooling (`build_fit.py`)
- **Depended on by:** gap classification (F8 §7 consumes intervals), reconciliation (F9 —
  the false `timer_time_s` discrepancy this fixes), moving time (§6)

## Related
- ADR: [0005 — timestamp policies](../architecture/adrs/0005-timestamp-policies.md) §5 (to be amended)
- Implementation: [docs/implementation/f45-timer-redundant-stop.md](../implementation/f45-timer-redundant-stop.md)
