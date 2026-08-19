---
description: Migration guide from fitdecode to chiptime — frame iteration to iter_frames/iter_messages mapping, field access, CRC options, and error-handling changes.
---

# Migrate from fitdecode

fitdecode is a clean frame-oriented reader, and its frame model maps almost
one-to-one onto chiptime's lower layers — then chiptime's semantic layer
covers the interpretation code you'd otherwise write on top.

## API mapping

| fitdecode | chiptime |
|---|---|
| `FitReader("a.fit")` + iterate frames | `chiptime.iter_frames("a.fit")` (wire) or `iter_messages` (decoded) |
| `frame.frame_type == FIT_FRAME_DATA` | messages from `iter_messages` *are* the data frames |
| `frame.name == "record"` | `msg.name == "record"` |
| `frame.get_value("hr", fallback=None)` | `msg.get("hr")` (absent → `None`) |
| `frame.get_field("hr").units` | `msg.fields["hr"].units` |
| `FitReader(..., check_crc=CrcCheck.WARN)` | default `lenient` (CRC triaged + reported) |
| `except FitHeaderError / FitEOFError:` | `result.errors` / `result.ok`; `strict` mode raises coded errors |
| your session/stream assembly code | `result.activity.sessions[*]` — already assembled, tested |

## Before / after

```python title="fitdecode"
import fitdecode

power = []
with fitdecode.FitReader("ride.fit") as fit:
    for frame in fit:
        if frame.frame_type == fitdecode.FIT_FRAME_DATA and frame.name == "record":
            v = frame.get_value("power", fallback=None)
            if v is not None:
                power.append(v)
```

```python title="chiptime"
import chiptime

result = chiptime.parse("ride.fit")
power = result.activity.sessions[0].records.stream("power")
# power.values: 0 W is coasting (real), None is dropout (absent) — kept distinct
```

## What you can delete after migrating

- Wrapper detection (gzip/zip) — chiptime unwraps and records it in
  `source.unwrapped`.
- Sentinel guards — invalid values are `None` before you ever see them.
- Session/lap/stream assembly, timer math, gap handling — the semantic layer
  ships them, with the edge cases (compressed timestamps, `timestamp_16`
  rollover, HR expansion) already handled.
