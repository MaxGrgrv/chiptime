---
description: "TRIM_BAD_BOUND: A trim bound could not be interpreted as a time; use an ISO timestamp or a relative offset like '+5m' / '-10m'. — what this chiptime error code means and how to handle it."
---

# `TRIM_BAD_BOUND`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**A trim bound could not be interpreted as a time; use an ISO timestamp or a relative offset like '+5m' / '-10m'.**

Error — the file violates the FIT structure this code names. In `lenient`/`forensic` mode it lands in `errors[]` on the result; in `strict` mode it raises a `chiptime.FitError` subclass carrying this code, a human `detail`, and (where useful) a `suggestion`.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "TRIM_BAD_BOUND":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `TRIM_BAD_BOUND`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
