---
description: See what a FIT file reveals about you — home location, device serials, body metrics — and remove it before sharing, with chiptime reveal and scrub.
---

# See what a file reveals, then remove it

A workout file carries more than a route. Alongside a GPS trace that usually
begins and ends at your front door, files routinely carry device serial
numbers and — depending on the device — age, gender, height, weight, resting
and max heart rate, threshold power. Most people have never seen this,
because nothing surfaces it. Then they email the file to a coach, or attach
it to a forum post asking why their watch is misbehaving.

## First, look

```bash
chiptime reveal ride.fit
```

```text
this file discloses:
  [serials] device_info.ant_device_number present in 22 message(s)
  [serials] device_info.serial_number present in 31 message(s)
  [serials] file_id.serial_number present in 1 message(s)
  [location] 9189 GPS points; the route starts and ends at real places
  route start ≈ 52.43, 13.75 · end ≈ 52.43, 13.74   (rounded to ~1 km so this report is safe to share)
  clean: identity, body_metrics
```

`reveal` writes nothing. It reports what is *actually* in your file and names
the categories that are genuinely clean — no scare-mongering about data that
isn't there.

!!! note "Why the coordinates are blurry"
    The report rounds positions to about a kilometre on purpose. These
    reports get pasted into the same forum threads the files do; a
    disclosure report that prints your doorstep would defeat itself.

## Then, remove it

```bash
chiptime scrub ride.fit -o clean.fit --gps-radius 500
```

```python
import chiptime

result = chiptime.scrub("ride.fit", gps_radius_m=500)
result.removed             # {'serials': 32, 'location': 482}
result.output_strict_ok    # True
open("clean.fit", "wb").write(result.data)
```

| Category | Default | What goes |
|---|---|---|
| `identity` | removed | `user_profile` — name, age, gender, height, weight |
| `serials` | removed | device serial numbers and ANT device ids |
| `body_metrics` | removed | configured physiology: threshold power, max/resting HR, VO2max |
| location | **kept unless asked** | GPS near your route's endpoints (`--gps-radius M`) or all of it (`--drop-all-gps`) |

Metadata categories are on by default because removing them costs you no
measurements. Location scrubbing is opt-in, because it does. Keep any
category with `--keep-identity`, `--keep-serials`, `--keep-body-metrics`.

## How location concealment works

`--gps-radius 500` hides every point within 500 m of the route's **first or
last** fix — *wherever it occurs in the ride*. That matters: a loop that
passes your house mid-route, or an out-and-back that touches home at the
turnaround, would leak if only the leading and trailing points were removed.

Concealed coordinates become **absent**, never `0` — "no reading" must not
turn into a point off the coast of Africa. Everything else on those records
(heart rate, power, distance) is preserved, and your totals are untouched:
distance is a recorded field, not something computed from coordinates.

## Your workout data stays your workout data

chiptime distinguishes fields that share a name but not a meaning.
`session.max_heart_rate` is the highest heart rate you *reached in that
workout* — that's training data, and it stays. `zones_target.max_heart_rate`
is your configured physiological maximum — that's personal, and it goes.

## What this does not promise

Scrubbing removes disclosed data; it does not make a file untraceable.
Distance, speed, and duration remain on concealed records, and a determined
analyst could infer a route's shape from them. If you need a file to be
genuinely anonymous, `--drop-all-gps` and a hard look at what's left is the
starting point, not `--gps-radius` alone.

## Check your work

```bash
chiptime scrub ride.fit -o clean.fit --gps-radius 500
chiptime reveal clean.fit          # confirm it discloses what you expect
chiptime validate clean.fit --platform garmin-connect
```
