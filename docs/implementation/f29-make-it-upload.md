# Implementation: F29 — `doctor` + distance calibration

> Spec: [features/f29-make-it-upload.md](../features/f29-make-it-upload.md) · 2026-08-21 · Ships in 0.8.0

## What was built

Three pieces answering one four-year-old question — *"I fixed it and the
platform still refuses it, and nothing tells me why."*

1. **`chiptime doctor FILE [--platform P] [--json]`**
   (`python/src/chiptime/doctor.py`) — reads a stubborn file and prints what
   is wrong, who cares, and the exact command that fixes it. Exit 0 clean,
   2 fixable, 3 no known fix.
2. **`VAL_GC_NO_TIMER_STOP`** — the checklist item our Garmin Connect
   profile was missing, shipped as a **warning** (see below).
3. **`edit --total-distance METRES`** — treadmill calibration, the recipe
   with documented demand that our `edit` verb could not serve.

```text
$ chiptime doctor broken.fit
broken.fit → garmin-connect
  parse ok · 90 records

  ✗ 3 blocking issue(s):
      VAL_GC_NO_SESSION: no session message (GC requires one)
      VAL_GC_NO_ACTIVITY: no activity message (GC requires one)
      VAL_GC_NO_LAP: no lap message (GC requires one)
  ! VAL_GC_NO_TIMER_STOP: activity has timer events but never a stop; Garmin Connect
    is reported to require a stop event (community-observed, not documented)

  try:
      chiptime repair broken.fit -o fixed.fit
        rebuilds the structure platforms require (file identity, timer events,
        session/lap/activity summaries) from the data that is actually there
```

## The prescription is measured, not asserted

A remedy that doesn't work is worse than no remedy, so the test suite
**executes the advice**: for three rejected fixtures it runs `doctor`, runs
the command `doctor` prescribed, and re-runs `doctor` on the result, which
must then report the file will upload. Verified during critique across four
files (3 errors → 0, 1 → 0, 3 → 0, 1 → 0 including a real Zwift crash file).

Findings with no remedy render under "no automatic fix" rather than
attracting a plausible-but-useless suggestion.

## The critique-mandated change: warning, not error

The spec proposed `VAL_GC_NO_TIMER_STOP` as a **blocking error**, on the
strength of a community-reverse-engineered checklist. Our validator profiles
encode *observed* platform behaviour, and this rule has a single second-hand
source with no documentation behind it. Shipping it as an error would
manufacture false rejections for files Garmin Connect actually accepts —
making the tool a liar in precisely the place users trust it most.

It ships as a warning whose text names its own provenance
("community-observed, not documented"). Promotion to error is BACKLOG'd
behind real evidence.

## Distance calibration keeps the file self-consistent

Setting a true distance scales the **record stream, speed, and the summaries
by the same factor** — scaling the total alone would produce exactly the
self-contradicting file F27 exists to prevent. Verified: a 5% calibration
moves average speed by exactly 5%, and a re-parse shows declared matching
derived.

Testing found an overflow the design missed: asking for 5,000 m on a 177 m
fixture is a 28× factor that blows past the uint16 speed field. There is now
a wire-type bounds check per field — the same guard the time-shift has —
raising `DISTANCE_SCALE_OUT_OF_RANGE` and writing no bytes. It names the
offending field and value rather than surfacing a raw struct error.

When no record distance stream exists (length-only pool files), calibration
falls back to the declared session total, which is the sensible reading.

## Verification
14 tests in `python/tests/test_doctor.py`: the executed-prescription loop
across three fixtures, clean-file silence, remedy dedup/ordering, unresolved
findings named honestly, deterministic JSON, the warning-level assertion,
calibration self-consistency, overflow refusal, declared-total fallback, and
CLI exit codes. Full gate green: ruff, format, mypy --strict, corpus,
132 tests, docs build.

## Deviations from spec
- `doctor --fix` (prescribe *and* execute) was cut at critique — prescribing
  and executing are different levels of consent. BACKLOG.
