---
description: "GPS_SPIKES_DROPPED: Physically impossible GPS bounce spikes removed (lenient) or flagged (forensic) (#53). — what this chiptime provenance code means and how to handle it."
---

# `GPS_SPIKES_DROPPED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Physically impossible GPS bounce spikes removed (lenient) or flagged (forensic) (#53).**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`gps/spike-bounce`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/gps/spike-bounce)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "GPS_SPIKES_DROPPED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `GPS_SPIKES_DROPPED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
