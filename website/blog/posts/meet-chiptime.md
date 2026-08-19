---
date: 2026-08-19
categories: [announcements]
description: chiptime 0.4 — FIT workout files in, clean data and analytics out. Zero dependencies, deterministic output, and recovery-grade robustness.
---

# Meet chiptime: your workout data, fully yours

Every sports watch and bike computer records into FIT files. Getting your
data *out* of them — cleanly, completely, and with analysis attached —
is what chiptime is for.

<!-- more -->

## FIT files in, answers out

```python
import chiptime
from chiptime import metrics

result = chiptime.parse("morning_ride.fit")
session = result.activity.sessions[0]

session.derived.distance_m           # totals recomputed from the actual data
session.records.stream("power")      # per-second streams, null-honest
report = metrics.analyze(result, metrics.AthleteSettings(ftp_w=250))
report.sessions[0].structure.repeats[0].label   # "3 x 10:00 @ 194 W rest 3:24"
```

One call parses any FIT file into a clean model — sessions, laps, swim
lengths, per-second columnar streams. The analytics layer speaks each
sport's language: pace and splits for runs, watts and weighted power for
rides, min/100m and sets for swims, /500m splits for rowing. Interval
structure is detected with named evidence, training load carries its basis,
and anything that would require guessing (thresholds, zones) is honestly
omitted instead.

## Built for imperfect files

Real files are messy: crashes mid-write, dead batteries, sensors dropping
out, firmware writing timestamps from 1989. chiptime treats robustness as a
first-class feature — damaged files parse instead of raising, `chiptime
repair` writes back a valid uploadable file, and every decision made about
your data is recorded in a machine-readable provenance log. Zero data loss
without a paper trail, ever.

## Built for pipelines and agents

Deterministic canonical JSON (same file → same bytes, any machine), stable
machine codes for every error and insight, meaningful exit codes, an
`llms.txt` manifest, and [generated API docs](../../reference/api-core.md).
If the consumer of your workout data is a program or an LLM, chiptime was
designed with it in mind.

## Get it

```bash
pip install chiptime
```

Python 3.11–3.14, zero runtime dependencies, MIT. Start with the
[five-minute tour](../../getting-started.md), or read
[the contract](../../concepts/contract.md) — the eight invariants that
govern every feature.
