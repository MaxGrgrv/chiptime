---
description: "DISTANCE_FROZEN: Distance frozen while moving; dead distance source (#59). — what this chiptime warning code means and how to handle it."
---

# `DISTANCE_FROZEN`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Distance frozen while moving; dead distance source (#59).**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "DISTANCE_FROZEN":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `DISTANCE_FROZEN`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
