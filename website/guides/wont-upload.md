---
description: Your FIT file won't upload to Garmin Connect or Strava and nothing says why. chiptime doctor diagnoses the file and prints the exact command that fixes it.
---

# "It won't upload and nothing tells me why"

This is the most common dead end in the FIT world. You have a file. A
platform refuses it — often *after* you already repaired it somewhere else,
and often while every other platform accepts it happily. The rejection
message, if there is one, says nothing useful.

```bash
chiptime doctor ride.fit
```

```text
ride.fit → garmin-connect
  parse ok · 3312 records · 29.61 km · 2 declared-vs-derived discrepancies

  ✗ 3 blocking issue(s):
      VAL_GC_NO_SESSION: no session message (GC requires one)
      VAL_GC_NO_ACTIVITY: no activity message (GC requires one)
      VAL_GC_NO_LAP: no lap message (GC requires one)

  try:
      chiptime repair ride.fit -o fixed.fit
        rebuilds the structure platforms require (file identity, timer events,
        session/lap/activity summaries) from the data that is actually there
```

Run the command it prints, then run `doctor` again on the result. That
round trip — diagnose, fix, confirm — is tested end-to-end in chiptime's
own suite, so the advice cannot quietly rot.

## Why files get rejected after being "repaired"

Most repair tools re-encode a file and, in doing so, quietly drop things the
strict consumer requires — the file identity block, device info, the timer
stop event, or the session/lap/activity summaries. The result satisfies a
lenient platform and fails a strict one, which is why "Strava took it,
Garmin didn't" is such a common shape.

chiptime's writes are held to an **identity round-trip**: re-encoding a file
without editing it must preserve every field value, asserted across the whole
conformance corpus including real multi-hour files. What you didn't ask to
change, doesn't change.

## Exit codes, for scripts and agents

| Exit | Meaning |
|---|---|
| 0 | Nothing blocking — it should upload |
| 2 | Blocked, but chiptime knows what to run |
| 3 | Blocked with no automatic fix (the findings say what to inspect) |

```bash
chiptime doctor ride.fit --json --platform strava
```

## Picking a platform

```bash
chiptime doctor ride.fit --platform garmin-connect   # default
chiptime doctor ride.fit --platform strava
chiptime doctor ride.fit --platform strict-spec      # the format itself, not a platform
```

The profiles encode *observed* platform behaviour. Where a rule is
community-reported rather than documented, chiptime says so in the finding
and keeps it advisory — a false rejection would be worse than a missing
check.

## When the numbers are wrong rather than the file

If a file uploads but the numbers are off, two other verbs apply:

- **Treadmill or footpod distance is wrong** — calibration doesn't travel
  inside the file, so fix it there:

  ```bash
  chiptime edit run.fit -o fixed.fit --total-distance 5000
  ```

  Records and speed scale by the same factor, so the stream and the summary
  still agree.

- **The device's totals disagree with its own records** — `chiptime parse`
  prints both, because different platforms silently trust different sides of
  that disagreement, which is why one ride can show four different numbers:

  ```text
  ascent_m: device says 86, records say 51.2 (delta -34.8)
  ```
