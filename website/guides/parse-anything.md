---
description: How chiptime parses corrupted, truncated, and damaged FIT files: recovery, resynchronization, provenance, and the null-vs-zero contract.
---

# Parse anything

chiptime's core promise: **any** FIT file produces a useful, honest result — including
files other tools reject.

```python title="three_lines.py"
import chiptime

result = chiptime.parse("mangled.fit")      # never raises in lenient mode
print(result.ok, result.recovery)           # what survived, what salvage did
print(result.activity.sessions[0].derived)  # totals recomputed from the data
```

## What "anything" means

- Truncated mid-write (device crash, dead battery) — salvage everything before the cut
- Corrupted blocks — resynchronize past the damage and keep reading
- Wrong or missing CRCs — triaged, reported, recovered
- Chained files (multiple FIT parts in one file) — each part parsed and reported
- Unknown messages, fields, and enum values from new devices — preserved, never fatal
- Vendor quirks — a catalog of real-world device bugs is handled explicitly

On one real damaged file, chiptime resynchronized 9 times past 39 KB of garbage and
recovered the ride.

## Recovery, reported

```python
result = chiptime.parse("damaged.fit")

result.recovery.recovered_records      # samples brought back
result.recovery.skipped_bytes          # what could not be read
for gap in result.activity.gaps:
    print(gap.kind, gap.duration_s)    # "corruption" | "auto_pause" | "manual_stop" | ...
```

Every gap in the timeline is classified with evidence — an auto-pause is not
corruption, and chiptime tells you which is which.

## Declared vs derived

Devices sometimes lie (firmware bugs, mid-file crashes). chiptime keeps both truths:

```python
s = result.activity.sessions[0]
s.declared.distance_m    # the device's claim (None if no session message survived)
s.derived.distance_m     # recomputed from the record stream
s.discrepancies          # [Discrepancy(field="distance_m", declared=..., derived=..., delta=...)]
s.rebuilt                # True when the session message was lost and rebuilt from records
```

## Streams: null is not zero

Record data comes out as columnar streams:

```python
rec = s.records
rec.streams.keys()                   # dict of every field any record carried
power = rec.stream("power")
power.values[:6]                     # [180, 0, 0, None, 195, 201]
power.present_count                  # samples that actually exist
```

`0, 0` is coasting — real measurements that belong in averages. `None` is a dropout —
absent, excluded from statistics. FIT sentinels (`0xFF` heart rate, `0xFFFF` power,
`0x7FFFFFFF` coordinates) are converted to `None` *before* anything downstream sees
them, so a sentinel can never masquerade as a 65,535 W sprint.

## Streaming large files

For bulk processing you can skip the semantic layer entirely:

```python
for msg in chiptime.iter_messages("big.fit"):     # constant memory
    if msg.name == "record":
        ...

for frame in chiptime.iter_frames("weird.fit"):   # wire-level forensics
    ...
```

## PII and output control

```python
chiptime.parse(data, strip_pii=True)       # drop GPS + athlete identity fields
chiptime.parse(data, include_raw=True)     # include raw wire values alongside decoded
chiptime.parse(data, include_unknown=False)
```
