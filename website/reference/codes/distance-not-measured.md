---
description: "DISTANCE_NOT_MEASURED: The file records no distance to rescale. — what this chiptime error code means and how to handle it."
---

# `DISTANCE_NOT_MEASURED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**The file records no distance to rescale.**

Error — the file violates the FIT structure this code names. In `lenient`/`forensic` mode it lands in `errors[]` on the result; in `strict` mode it raises a `chiptime.FitError` subclass carrying this code, a human `detail`, and (where useful) a `suggestion`.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "DISTANCE_NOT_MEASURED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `DISTANCE_NOT_MEASURED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
