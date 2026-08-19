---
description: "LAP_ZERO_DURATION: Zero-duration laps; double button press (#94). — what this chiptime warning code means and how to handle it."
---

# `LAP_ZERO_DURATION`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Zero-duration laps; double button press (#94).**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`reconcile/zero-duration-lap`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/reconcile/zero-duration-lap)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "LAP_ZERO_DURATION":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `LAP_ZERO_DURATION`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
