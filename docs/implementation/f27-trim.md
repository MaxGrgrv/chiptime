# Implementation: F27 — `trim`

> Spec: [features/f27-trim.md](../features/f27-trim.md) · 2026-08-21 · Ships in 0.6.0

## What was built

`python/src/chiptime/trim.py` — `trim(src, *, after, before, mode) -> TrimResult`,
plus the `chiptime trim` CLI verb.

The feature is two acts, and the second is the point:

1. **Filter** records, pool lengths, laps, and events against the window.
2. **Rebuild** every number that depended on them — session and activity
   summaries are recomputed from the survivors, never carried over.

```text
TRIM_RECORDS_DROPPED: dropped 292 record(s) and 9 pool length(s) outside the requested window
TRIM_LAP_DROPPED: dropped 3 lap(s) not wholly inside the window; their in-window records are kept
TRIM_SUMMARIES_REBUILT: session and activity totals recomputed from the 3171 surviving record(s)
```

### One selection model
`after` / `before` each accept an absolute `datetime`, an ISO string, or a
relative offset: `"+5m"` (five minutes after the start — cut the warm-up) and
`"-10m"` (ten minutes before the end — cut the drive home). Tested for exact
equivalence with the absolute datetime each resolves to.

### Structure kept where it is still true
- Laps **wholly inside** the window survive untouched, because their declared
  totals remain correct — so interval structure is preserved.
- Laps straddling a boundary are dropped with their `message_index` recorded;
  their in-window records survive.
- The synthesized session references `first_lap_index = min(kept)` and
  `num_laps = len(kept)`, via new parameters on `repair._summary_message` —
  one implementation, two callers, no fork.

## The two critique-mandated changes, as built

**1. No encode/re-parse round trip.** The spec proposed writing an
intermediate summary-less file and re-parsing it to recompute totals. That
works (verified: a records-only file re-parses into a rebuilt session with
correct totals), but measurement showed the cost: on the 72,924-message
multisport file, parse is ~1.4 s and encode ~1.7 s, so the round trip would
have **doubled** a ~3 s operation for no correctness gain. `build_activity()`
is already a pure function of a message list, so trim calls it directly.

**2. In-window timer events are preserved.** Rebuilding *all* events would
have erased auto-pause and manual-stop structure inside the kept window — and
because the semantic layer classifies gaps from those events, moving time
would have silently inflated after trimming an unrelated region. Events are
now filtered like records; start/stop is synthesized only when none survive.

## Honest limits (found by testing against real fixtures)
- **Length-only pool files** (lengths, no records) refuse with
  `TRIM_NO_RECORDS` and a plain explanation: session totals cannot be rebuilt
  from lengths alone, and carrying a stale summary forward is exactly the lie
  this feature exists to prevent. Real watches write records alongside
  lengths — the private-tier pool swim (3,463 records, 81 lengths) trims
  correctly, dropping 292 records and 9 lengths with totals rebuilt from
  1,475 m to 1,325 m.
- Straddling-lap truncation, middle-section splicing, and distance rebasing
  are deferred (BACKLOG, with triggers).

## Verification
- 13 tests in `python/tests/test_trim.py`. The central assertion is that the
  output's **declared** totals equal what its own surviving records **derive**
  — i.e. the trimmed file cannot lie — checked on both a ride and a real pool
  swim, alongside lap preservation, event preservation, determinism, refusals
  (empty window, no window, bad bound, length-only), platform validation, and
  the CLI.
- Full gate green: ruff, format, mypy --strict, corpus (72 cases), 104 tests.

## Deviations from spec
- Bounds resolution also considers pool lengths (not just records) so swim
  files are handled coherently; the length-only refusal above is explicit.
