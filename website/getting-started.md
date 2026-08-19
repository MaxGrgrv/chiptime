---
description: Install chiptime and go from parsing a FIT file to a repaired upload and a per-sport workout report in five minutes.
---

# Getting started

## Install

=== "pip"

    ```bash
    pip install chiptime
    ```

=== "uv"

    ```bash
    uv add chiptime
    ```

Python ≥ 3.11. The core has **zero runtime dependencies** — nothing else comes with it.
The optional `chiptime[pandas]` extra enables `Records.to_pandas()`.

## Parse your first file

```python
import chiptime

result = chiptime.parse("morning_run.fit")

result.ok                # True if the file yielded usable content
result.file_type         # "activity", "course", "workout", "monitoring", ...
result.mode              # "lenient" — the default
```

`parse` accepts a path, `bytes`, or a binary file object. It never raises on damaged
input in the default mode — problems become structured `errors` / `warnings` on the
result instead.

## Walk the workout

```python
activity = result.activity
session = activity.sessions[0]

session.sport                       # "running"
session.derived.distance_m          # recomputed from the data
session.declared.distance_m         # what the device claimed
session.discrepancies               # where those two disagree

records = session.records
records.n                           # number of samples
hr = records.stream("heart_rate")
hr.values[:5]                       # [142, 143, None, 144, 145]
```

That `None` is the point: **null means the sensor said nothing; `0` means it said
zero.** Coasting at 0 W is real data; a dropout is absence. chiptime never conflates
them, so a `0xFFFF` sentinel can never poison an average.

## Three modes, one switch

| Mode | Philosophy | Use when |
|---|---|---|
| `lenient` (default) | Recover what's recoverable, warn about the rest | Almost always |
| `strict` | Spec lawyer — raise on the first violation | Validating writers/pipelines |
| `forensic` | Maximum salvage, every byte accounted for | Damaged files, investigations |

```python
chiptime.parse(data, mode="strict")     # raises chiptime.FitError subclasses
chiptime.parse(data, mode="forensic")   # never gives up, annotates everything
```

## Read the paper trail

```python
for entry in result.provenance:
    print(entry.code, "-", entry.detail)
# RESYNC_SKIPPED_BYTES - skipped 39424 unreadable bytes at offset 129812
# SESSION_REBUILT - session synthesized from 9190 records (no session message)
```

Everything chiptime dropped, repaired, or reinterpreted is in `provenance` —
machine-coded, human-readable, and present in the JSON output too.

## Get JSON out

```python
payload = result.to_canonical_json()    # bytes, RFC 8785 canonical form
```

The same file produces the same bytes on every machine, every time — see
[Determinism](concepts/determinism.md).

## Fix a broken file

```python
fixed = chiptime.repair("crashed.fit")
fixed.output_strict_ok                  # True: the repaired file parses strictly
open("fixed.fit", "wb").write(fixed.data)
```

## Analyze a workout

```python
from chiptime import metrics

report = metrics.analyze(result, metrics.AthleteSettings(ftp_w=250))
ses = report.sessions[0]
ses.pace          # {"seconds": 300.1, "style": "per_km", "formatted": "5:00/km", "basis": "moving"}
ses.structure.repeats[0].label          # "6 x 0:30 @ 300 W rest 0:30"
ses.load          # LoadEstimate(value=87.4, basis="power+ftp", ...)
ses.insights      # [Insight(code="PACING_NEGATIVE_SPLIT", ...)]
ses.omissions     # what was NOT computed, and why
```

Next: [Parse anything](guides/parse-anything.md) ·
[Analyze workouts](guides/analyze.md) · [Built for agents](guides/agents.md)
