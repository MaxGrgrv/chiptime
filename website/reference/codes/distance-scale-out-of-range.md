---
description: "DISTANCE_SCALE_OUT_OF_RANGE: Rescaling distance by the requested factor would overflow a field's wire type; nothing was written. — what this chiptime error code means and how to handle it."
---

# `DISTANCE_SCALE_OUT_OF_RANGE`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Rescaling distance by the requested factor would overflow a field's wire type; nothing was written.**

Error — the file violates the FIT structure this code names. In `lenient`/`forensic` mode it lands in `errors[]` on the result; in `strict` mode it raises a `chiptime.FitError` subclass carrying this code, a human `detail`, and (where useful) a `suggestion`.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "DISTANCE_SCALE_OUT_OF_RANGE":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `DISTANCE_SCALE_OUT_OF_RANGE`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
