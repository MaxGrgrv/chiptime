---
description: "TIMER_REDUNDANT_STOP: Timer stop arrived with no interval open; ignored as redundant (device shutdown / multisport boundary pattern). — what this chiptime provenance code means and how to handle it."
---

# `TIMER_REDUNDANT_STOP`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Timer stop arrived with no interval open; ignored as redundant (device shutdown / multisport boundary pattern).**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`multisport/boundary-timer-events`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/multisport/boundary-timer-events) · [`temporal/redundant-stop-shutdown`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/temporal/redundant-stop-shutdown)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "TIMER_REDUNDANT_STOP":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `TIMER_REDUNDANT_STOP`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
