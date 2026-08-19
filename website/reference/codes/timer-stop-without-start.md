---
description: "TIMER_STOP_WITHOUT_START: Timer stop event had no preceding start; interval opened at first record. — what this chiptime warning code means and how to handle it."
---

# `TIMER_STOP_WITHOUT_START`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Timer stop event had no preceding start; interval opened at first record.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "TIMER_STOP_WITHOUT_START":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `TIMER_STOP_WITHOUT_START`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
