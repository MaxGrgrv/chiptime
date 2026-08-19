---
description: "DISTANCE_DECREASES: Distance stream decreases (#59). — what this chiptime warning code means and how to handle it."
---

# `DISTANCE_DECREASES`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Distance stream decreases (#59).**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`sensors/hr-power-distance-anomalies`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/sensors/hr-power-distance-anomalies) · [`structural/garbage-block-midfile`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/structural/garbage-block-midfile)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "DISTANCE_DECREASES":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `DISTANCE_DECREASES`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
