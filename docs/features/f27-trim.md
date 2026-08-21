# Feature: F27 — `trim`: crop an activity without letting the file lie

> Status: DONE

## Purpose

The most-requested edit after metadata (research: `docs/internal/research-fit-jobs-2026-08.md`,
job #4, HIGH): *"I forgot to stop my watch"*, *"I drove home while
recording"*, *"cut the warm-up"*. Platforms ship crop tools; standalone
croppers exist for nothing else.

Cropping is easy. Cropping **without leaving a file that lies about itself**
is the hard part: once records disappear, every summary computed from them —
session totals, activity totals, timer events, averages — is wrong until it
is rebuilt. A trimmed file with stale totals is worse than no trim at all,
because the error is invisible and travels downstream forever.

chiptime is unusually well positioned: the semantic layer already recomputes
totals from records (`derived`), and F13 already synthesizes summary messages
from a session. F27 composes them: **filter the records, then rebuild every
number that depended on them.**

## Context Check
- [x] docs/INDEX.md — no existing feature crops; F13 repairs, F26 edits metadata
- [x] docs/architecture/OVERVIEW.md — write layer, beside `edit.py`/`repair.py`
- [x] docs/dependencies/DEPENDENCY_MAP.md — no cycles (depends on decode/semantics/encode)
- [x] docs/PRD.md — user-directed write, same footing as F26 (amended non-goal)
- [x] docs/edge-case-taxonomy.md — touches #50 (lap end_time), #95 (session rebuild)
- [x] No duplication

## Taxonomy Coverage

Write-side feature; it does not add parser behavior. It *exercises* existing
items and must not regress them:

| Taxonomy item # | Summary | Corpus case(s) |
|---|---|---|
| 50 | Lap `end_time` is start + elapsed, never the write timestamp | existing `reconcile/*`; asserted in trim tests |
| 95 | Session rebuilt from records when absent | existing `reconcile/no-session-rebuild` (reused as fixture) |

No new corpus inputs planned — the trim assertions run against committed
cases (`clean/ride-smooth`, `multisport/triathlon`, `swim/pool-lengths`).
See the F26 precedent for why duplicating inputs under a verb prefix adds
weight without coverage.

## Requirements

1. **API**: `chiptime.trim(src, *, after=None, before=None, mode="lenient")
   -> TrimResult{data, provenance, output_strict_ok, records_kept,
   records_dropped, parse_result}`.
2. **One selection model**, covering every asked-for case:
   `after` / `before` each accept an absolute `datetime`, or a relative
   offset — `+5m` (5 minutes after the activity starts) or `-10m` (10 minutes
   before it ends). So "cut the first 5 minutes" is `after="+5m"` and "cut
   the last 10" is `before="-10m"`.
3. **Records and pool lengths outside the window are dropped**, with exact
   counts in provenance (`TRIM_RECORDS_DROPPED`). Explicitly-requested
   deletion is not silent loss — but it must be *stated*.
4. **Laps**: kept unchanged when they fall entirely inside the window (their
   declared totals are still true); dropped when entirely outside; a lap
   straddling a boundary is dropped with provenance while its in-window
   records survive. Interval structure is preserved in the common case
   without inventing per-lap arithmetic that does not exist yet.
5. **Session and activity summaries are always rebuilt** from the surviving
   records — never carried over. This is the feature's core promise.
6. **Timer events** are resynthesized at the new bounds so the file has a
   coherent start/stop.
7. **Record measurements are never rewritten.** Cumulative distance keeps its
   recorded values; the session total is correct regardless because derived
   distance is `last − first`. Rebasing the stream to zero would be editing
   measurements — out of scope (BACKLOG).
8. **Refuse to trim everything**: an empty keep-window raises
   `TRIM_EMPTY_RESULT` and writes no bytes.
9. **CLI**: `chiptime trim FILE -o OUT [--after X] [--before Y]`; exit 64
   when neither bound is given.
10. Output re-parsed in `strict` mode (`output_strict_ok`), as with
    `repair`/`edit`.

## Acceptance Criteria
- [ ] Trimming the first N seconds drops exactly the expected records and the
      rebuilt session totals match a fresh parse of the output (no stale numbers)
- [ ] Trimming the tail of a multi-lap file preserves fully-contained laps and
      drops only the straddling one, with provenance
- [ ] Pool lengths outside the window are dropped (swim fixture)
- [ ] `output_strict_ok` true; output passes `validate --platform garmin-connect`
      where the input did
- [ ] Distance/elapsed/timer totals of the output equal the values derived from
      the surviving records — asserted numerically, not by eyeball
- [ ] Empty window refuses with `TRIM_EMPTY_RESULT` and writes nothing
- [ ] Determinism: identical trim twice → byte-identical output

## Public API Impact
- **New**: `chiptime.trim`, `chiptime.TrimResult`; `chiptime trim` CLI verb;
  provenance codes `TRIM_RECORDS_DROPPED`, `TRIM_LAP_DROPPED`,
  `TRIM_SUMMARIES_REBUILT`; error `TRIM_EMPTY_RESULT`.
- **Canonical JSON schema**: unchanged.

## Architectural Placement

`python/src/chiptime/trim.py`, write layer, beside `edit.py` and `repair.py`.
Reuses `repair`'s summary synthesis rather than duplicating totals maths.

## Proposed Approach

1. Parse; resolve the window against the activity's own bounds.
2. Partition messages: keep file_id/device_info/etc., filter records and
   lengths by timestamp, classify laps, discard stale session/activity/lap
   summaries and timer events.
3. Encode the survivors into an intermediate summary-less file.
4. **Re-parse it** so the semantic layer recomputes `derived` totals from the
   survivors, then synthesize session/lap/activity/events from that session —
   exactly the path `repair` already walks. Correct by construction: there is
   no second implementation of totals arithmetic to drift.
5. Strict self-check; return `TrimResult`.

## Dependencies
- **Depends on:** F3 decode, F7/F9 semantics (derived totals, rebuild),
  F12 encoder, F13 repair (synthesis path), F11 CLI
- **Depended on by:** F28 (privacy scrub reuses window logic), F30 (merge)

## Critique & Assessment

### Necessity — PASS
HIGH-frequency job with independent evidence; platforms and standalone tools
exist for nothing else. Not building it leaves the most common "my file is
wrong" case unserved by the one library that could crop *honestly*.

### Placement — PASS
Write layer beside `edit.py`/`repair.py`. Rejected alternative: a `--trim`
flag on `repair` — repair means "restore what broke", trim means "remove what
I asked for"; conflating them makes provenance unreadable.

### Approach — REVISED after measurement
The spec proposed encoding an intermediate summary-less file and re-parsing
it so the semantic layer recomputes totals. Verified empirically:

- **The pivot is sound**: a records-only file re-parses into a rebuilt
  session with correct derived totals (distance 991.27 m, elapsed 119 s,
  avg HR 139.5 on `clean/ride-smooth`) — confirming totals never need a
  second implementation.
- **But the cost is real**: on the 72,924-message multisport file, parse is
  ~1.4 s and encode ~1.7 s, so the round trip adds **~3 s** to a ~3 s
  operation — doubling it for no correctness gain.

**⛔ Required change 1**: call `semantics.build_activity(messages, …)`
directly on the filtered message list instead of encoding and re-parsing.
Same single source of totals arithmetic, one encode and one parse saved.
The builder is already a pure function of a message list — this was simply
the wrong seam to cut.

### ⛔ Required change 2 — do not discard in-window timer events
The spec said summaries and timer events are rebuilt. Rebuilding *all*
events would erase auto-pause and manual-stop structure in the middle of the
kept window, and the semantic layer classifies gaps from exactly those
events — so moving time would silently inflate after a trim of an unrelated
region. That is a contract #1 violation dressed as a simplification.
**Revised**: keep every in-window event; drop only out-of-window ones;
synthesize start/stop *only* when none survive.

### Risks
- **Straddling laps**: dropped, leaving in-window records not covered by a
  lap. Common in real files and accepted by platform validators (asserted in
  the acceptance criteria). Truncating them properly needs per-lap derived
  totals, which do not exist yet → BACKLOG.
- **Lap indices**: kept laps retain their original `message_index`, so a
  synthesized session must reference `first_lap_index = min(kept)` and
  `num_laps = len(kept)` rather than repair's hardcoded `0/1`. Extend
  `repair._summary_message` with those parameters instead of forking it —
  one implementation, two callers.
- **Blast radius**: additive module; the only shared change is the
  `_summary_message` signature, covered by existing repair corpus cases.

### Contract check
- Silent loss: deletion is the user's explicit request, but counts and
  dropped laps are itemized in provenance. Passes only *because* of that.
- Determinism: filtering is order-preserving; no clock, no randomness.
- Sentinels/zero-vs-null: untouched — measurements are never rewritten.
- Modes: inherited from the read; `strict` refuses to trim a file that does
  not parse strictly (consistent with `edit`).
- Errors: `TRIM_EMPTY_RESULT` carries code + sentence + suggestion.
- Corpus: no new inputs; assertions run against committed cases. Consistent
  with the F26 precedent and contract #7 (no new taxonomy claims made).

### Simplification
- Middle-section removal (cut out the middle and splice) is **cut** — it
  creates a deliberate time gap and raises questions trimming does not
  (renumber? leave a hole? re-time?). BACKLOG.
- Distance rebasing to zero is **cut**: derived distance is `last − first`,
  so totals are already correct; rebasing would edit measurements. BACKLOG
  behind a flag if platform rendering proves it necessary.
- The 20%/80% version is `--after`/`--before` with rebuilt summaries, which
  is what remains.

### Final decision: **APPROVE** — conditional on required changes 1 and 2

## Related
- Implementation: `docs/implementation/f27-trim.md`
