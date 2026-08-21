---
description: Crop a FIT activity — cut the warm-up, the drive home, or a forgotten stop — and have every total rebuilt so the file doesn't lie.
---

# Trim an activity

You forgot to stop your watch. You drove home while it was still recording.
You want the warm-up gone. Cropping is the fix — but a cropped file whose
totals still describe the *old* activity is worse than no crop at all,
because the error is invisible and follows the file forever.

```bash
chiptime trim ride.fit -o cropped.fit --before -10m     # cut the last 10 minutes
```

```text
TRIM_RECORDS_DROPPED: dropped 292 record(s) outside the requested window
TRIM_SUMMARIES_REBUILT: session and activity totals recomputed from the 3171 surviving record(s)
wrote cropped.fit (58124 bytes; 3171 records kept, 292 dropped)
```

## One way to say what you want

`--after` and `--before` both accept an absolute time **or** a relative
offset, which covers every common case with one idea:

| You want | Say |
|---|---|
| Cut the first 5 minutes | `--after +5m` |
| Cut the last 10 minutes | `--before -10m` |
| Keep only the middle | `--after +5m --before -10m` |
| Cut from an exact moment | `--after 2026-06-01T09:15:00Z` |

Offsets take `s`, `m`, or `h`; `+` counts from the start of the activity and
`-` counts back from the end.

```python
import chiptime

result = chiptime.trim("ride.fit", after="+5m")
result.records_kept, result.records_dropped
result.output_strict_ok          # the output re-parsed in strict mode
open("cropped.fit", "wb").write(result.data)
```

## Every total is rebuilt

This is the part that matters. When records disappear, distance, duration,
and averages computed from them are stale — so chiptime recomputes session
and activity summaries from exactly the records that survived, using the same
semantic layer that computes totals during a normal parse. The output's
declared totals always equal what its own data proves.

## Structure is kept where it's still true

- **Laps wholly inside** the window survive untouched — their totals are
  still correct, so interval structure is preserved.
- **A lap straddling a boundary** is dropped and reported by
  `message_index`; its in-window records are kept.
- **Timer events inside the window are preserved**, so auto-pause and
  manual-stop structure survives a trim of an unrelated part of the ride.
  Without that, moving time would quietly inflate.

## What it refuses to do

Trimming never rewrites a measurement. Cumulative distance keeps its recorded
values — the session total is still correct, because it is derived as
last − first.

chiptime refuses rather than guess when it cannot rebuild honestly:

| Situation | Result |
|---|---|
| The window keeps nothing | `TRIM_EMPTY_RESULT`, no bytes written |
| No `--after` or `--before` given | usage error (exit 64) |
| A bound it can't interpret | `TRIM_BAD_BOUND`, with the accepted forms |
| A length-only pool file (no records) | `TRIM_NO_RECORDS` — totals can't be rebuilt from lengths alone |

## Check before you upload

```bash
chiptime trim ride.fit -o cropped.fit --after +5m
chiptime validate cropped.fit --platform garmin-connect
```
