# ADR-0005: Timestamp policies — ordering, anchors, sanity flags

> Status: ACCEPTED · 2026-08-18 · Feature: F8

## Context
Taxonomy section C: non-monotonic records (#41), duplicate seconds (#42), gap
semantics (#43/#44), unreliable absolute time (#39/#40), the Zwift
local_timestamp bug (#37). Policies must be explicit, deterministic, and
recorded in output — never silent (#41: "sort vs drop vs re-anchor = explicit
policy; record the decision").

## Decisions
1. **Ordering: stable sort, never drop.** Records are stably sorted by
   timestamp for the semantic timeline; equal timestamps keep file order
   (deterministic tie-break, #42). Records without timestamps inherit the
   previous record's key (carry-forward) so they stay adjacent. When sorting
   changed the order, provenance `RECORDS_REORDERED` records how many moved.
   The lossless message layer keeps original file order untouched.
2. **No wall clock, ever** (determinism contract). "Future timestamp" (#40)
   is therefore approximated deterministically: record timestamps more than
   7 days after `file_id.time_created` raise `TIMESTAMPS_AFTER_CREATION`.
3. **Sane floor** (#39): any record before 2010-01-01 UTC → warning
   `UNRELIABLE_ABSOLUTE_TIME` (once). Relative timeline is kept untouched;
   re-anchoring is a repair-layer (M2) option, never automatic.
4. **local_timestamp validation** (#37): with both `activity.timestamp` and
   `activity.local_timestamp` raws present, the offset must be within ±26 h
   (max real zone ±14 h + margin) and is exposed as `Activity.utc_offset_s`.
   Outside that — or when local is device-relative (< 0x10000000, the Zwift
   1989 bug) — `utc_offset_s = None` + warning `LOCAL_TIMESTAMP_IMPLAUSIBLE`.
   Local-time math never mutates the UTC stream (#47).
5. **Timer machine** (#45): start/stop(_all) build running intervals.
   Stop-without-start opens an interval at the first record (warning
   `TIMER_STOP_WITHOUT_START`) — but only for the genuine crash class: no
   intervals built yet AND the first record strictly precedes the stop.
   Otherwise the stop is redundant — device shutdown writes `stop_all` after
   the final stop (Wahoo ELEMNT), and multisport slicing leaks a session's
   boundary stop into the next session's window (Suunto) — and is a no-op
   recorded as provenance `TIMER_REDUNDANT_STOP` (F45). A missing final stop
   closes at the last record (provenance `TIMER_STOP_SYNTHESIZED`) — only when
   the close yields a non-empty interval; a dangling start at/after the last
   record is the boundary leak's mirror image and is a no-op recorded as
   `TIMER_REDUNDANT_START`. `derived.timer_time_s` = interval sum.
6. **Moving time** (#46): within running intervals, per-record dt (capped at
   30 s) counts as moving when speed > 0.1 m/s; with no speed stream, moving
   time is honestly None — never guessed from positions in M1.
7. **Gap classification** (#43/#44): consecutive-record dt ≥ 10 s becomes a
   `Gap`: overlapping a stopped interval → `manual_stop` or `auto_pause` (from
   the stop event's timer_trigger data); after the final stop → `post_timer`;
   dt ≤ 30 s with no events → `smart_recording`; records straddling a
   resynchronized byte range → `corruption`; else `unknown`. Never interpolated.

## Consequences
- Every temporal decision is visible in output; the JS port re-implements
  policies from this ADR + corpus cases, not from code reading.
- #40 detection is weaker than wall-clock comparison — accepted for
  determinism; repair tooling (M2) may use caller-provided "now".
