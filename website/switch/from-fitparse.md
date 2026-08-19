---
description: Migration guide from fitparse to chiptime — side-by-side API mapping for messages, fields, units, error handling, and the behavior differences to expect.
---

# Migrate from fitparse

Most fitparse scripts translate line-for-line. The mental shift: fitparse
gives you messages to iterate; chiptime *also* gives you the interpreted
workout (sessions, streams, totals) so most loops disappear.

fitparse is a long-standing, widely used library — this guide is mechanics,
not a verdict. If your current setup works, it works.

## API mapping

| fitparse | chiptime |
|---|---|
| `FitFile("a.fit")` | `chiptime.parse("a.fit")` |
| `ff.get_messages("record")` | `(m for m in result.messages if m.name == "record")` — or skip straight to streams |
| `rec.get_value("heart_rate")` | `msg.get("heart_rate")` |
| `field.value`, `field.raw_value` | `fv.value`, `fv.raw` (`msg.fields["heart_rate"]`) |
| `field.units` | `fv.units` or `stream.units` |
| `FitFile(..., check_crc=False)` | default `lenient` mode (CRC triaged + reported, not fatal) |
| `try: ... except FitParseError:` | check `result.ok` / `result.errors` (nothing raises in lenient) |
| manual semicircle → degrees | `position_lat`/`position_long` streams already in degrees |
| loop-and-collect per field | `session.records.stream("power").values` — already columnar |

## Before / after

```python title="fitparse"
import fitparse

ff = fitparse.FitFile("ride.fit", check_crc=False)
hr = []
for record in ff.get_messages("record"):
    v = record.get_value("heart_rate")
    if v is not None and v != 255:          # sentinel guard, by hand
        hr.append(v)
avg = sum(hr) / len(hr) if hr else None
```

```python title="chiptime"
import chiptime

result = chiptime.parse("ride.fit")          # damaged files included
s = result.activity.sessions[0]
avg = s.derived.avg.get("heart_rate")        # sentinels were never values
```

## What changes

- Files that raise in fitparse may parse in chiptime's `lenient` mode —
  check `result.ok` and `provenance[]` instead of wrapping in try/except.
- `None` always means absent in chiptime streams; zero is a real value.
- Multi-part files and gzip-wrapped exports are unwrapped automatically.
- If you want raise-on-problem semantics: `chiptime.parse(data, mode="strict")`
  raises coded exceptions on the first violation.

## Streaming equivalence

If you used fitparse for constant-memory iteration, the direct analog is:

```python
for msg in chiptime.iter_messages("big.fit"):
    if msg.name == "record":
        ...
```
