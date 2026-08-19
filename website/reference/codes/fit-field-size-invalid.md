---
description: "FIT_FIELD_SIZE_INVALID: A field's size is not a multiple of its base type size. — what this chiptime error code means and how to handle it."
---

# `FIT_FIELD_SIZE_INVALID`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**A field's size is not a multiple of its base type size.**

Error — the file violates the FIT structure this code names. In `lenient`/`forensic` mode it lands in `errors[]` on the result; in `strict` mode it raises a `chiptime.FitError` subclass carrying this code, a human `detail`, and (where useful) a `suggestion`.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "FIT_FIELD_SIZE_INVALID":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `FIT_FIELD_SIZE_INVALID`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
