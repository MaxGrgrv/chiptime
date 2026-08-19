---
description: "HR_FLATLINE: Heart rate flatlined for 2+ minutes; sensor suspect (#62). — what this chiptime warning code means and how to handle it."
---

# `HR_FLATLINE`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Heart rate flatlined for 2+ minutes; sensor suspect (#62).**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`multisport/triathlon`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/multisport/triathlon) · [`sensors/hr-power-distance-anomalies`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/sensors/hr-power-distance-anomalies)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "HR_FLATLINE":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `HR_FLATLINE`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
