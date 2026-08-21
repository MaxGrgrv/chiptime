---
description: Change what a FIT file says about itself — sport, recording device, timestamps — and keep it uploadable. chiptime edit with a validated round-trip.
---

# Edit a file's metadata

Sometimes the measurements are fine but the *labels* are wrong: an activity
recorded as the wrong sport, a trainer ride whose device identity stops a
platform counting it, a file whose clock was hours off.

```bash
chiptime edit ride.fit -o fixed.fit --sport running
```

```python
import chiptime

result = chiptime.edit("ride.fit", sport="running")
result.output_strict_ok        # True — the output re-parsed in strict mode
result.provenance              # exactly what changed, before → after
open("fixed.fit", "wb").write(result.data)
```

!!! info "Why edit the file instead of the platform?"
    Platform "edit activity" UIs change the platform's own database — the
    file still says the old thing, so every re-export and re-import carries
    the error forward. Editing the file is the durable fix.

## What you can change

| Flag / argument | Changes |
|---|---|
| `--sport` / `sport=` | The declared sport, everywhere it appears (sport, session, lap, workout messages) |
| `--sub-sport` / `sub_sport=` | The sub-sport — only when you name it; never inferred |
| `--manufacturer` / `manufacturer=` | The recording device's manufacturer, by name (`garmin`) or number (`1`) |
| `--product` / `product=` | The product id (numeric — product ids are vendor-specific) |
| `--time-shift` / `time_shift_s=` | Signed offset applied to every timestamp: seconds or `±HH:MM` |

This verb is **metadata only**. It never touches a measurement — no
distances, no heart rates, no positions.

## The guarantee that matters: it still uploads

Editing a FIT file is easy; editing one that platforms still accept is not.
Every edit goes through the same encoder that powers
[`repair`](repair.md), then the result is **re-parsed in strict mode** before
you ever see it:

```python
result.output_strict_ok    # False means: inspect before uploading
```

Everything you did not name round-trips untouched — including unknown
messages, unknown enum values from devices newer than this release, and
developer fields from third-party sensors. That is asserted by tests that
compare the input and output field-by-field and fail on any collateral
change.

## Sport and sub-sport

```bash
chiptime edit hike.fit -o run.fit --sport running --sub-sport generic
```

Changing sport rewrites it in *every* message that declares one, so the file
cannot end up internally contradictory. If you change the sport and leave a
specific sub-sport in place, chiptime warns rather than guessing a
replacement:

```text
SPORT_PAIR_IMPLAUSIBLE: sport changed to 'running' while sub_sport stays 'road_biking'
```

chiptime flags; it does not decide for you. Name the `--sub-sport` you want.

## Device identity

```bash
chiptime edit trainer_ride.fit -o fixed.fit --manufacturer garmin --product 2480
```

Only the *recording* device is rewritten — `file_id` and the creator entry in
`device_info`. Sensor entries are left alone, because a heart-rate strap did
not create the file.

## Time shift

```bash
chiptime edit ride.fit -o shifted.fit --time-shift +01:30    # or --time-shift 5400
```

Every timestamp the FIT profile knows about moves by exactly the offset, so
**relative spacing is preserved** and the local/UTC pairing keeps its offset.
Fields chiptime doesn't recognize are left alone — it cannot know an unknown
field is a timestamp, and guessing would corrupt data.

If a shift would push any timestamp outside the representable FIT range — or
onto the invalid sentinel, which would silently turn a real timestamp into
"no reading" — the whole edit is refused and **no bytes are written**:

```text
TIME_SHIFT_OUT_OF_RANGE: shifting record.timestamp by 4294967294s would move it
to 5444206094, outside the representable FIT range [0, 4294967294]
```

## Verify before you upload

```bash
chiptime edit ride.fit -o fixed.fit --sport running
chiptime validate fixed.fit --platform garmin-connect
```
