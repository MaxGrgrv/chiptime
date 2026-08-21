---
description: "TRIM_EMPTY_RESULT: The requested trim window keeps no data; nothing was written. — what this chiptime error code means and how to handle it."
---

# `TRIM_EMPTY_RESULT`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**The requested trim window keeps no data; nothing was written.**

Error — the file violates the FIT structure this code names. In `lenient`/`forensic` mode it lands in `errors[]` on the result; in `strict` mode it raises a `chiptime.FitError` subclass carrying this code, a human `detail`, and (where useful) a `suggestion`.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "TRIM_EMPTY_RESULT":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `TRIM_EMPTY_RESULT`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
