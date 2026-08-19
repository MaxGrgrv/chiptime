---
description: "REPAIR_NOTHING_TO_SALVAGE: Nothing usable survives parsing; repair refuses to fabricate data (#16). — what this chiptime error code means and how to handle it."
---

# `REPAIR_NOTHING_TO_SALVAGE`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Nothing usable survives parsing; repair refuses to fabricate data (#16).**

Error — the file violates the FIT structure this code names. In `lenient`/`forensic` mode it lands in `errors[]` on the result; in `strict` mode it raises a `chiptime.FitError` subclass carrying this code, a human `detail`, and (where useful) a `suggestion`.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "REPAIR_NOTHING_TO_SALVAGE":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `REPAIR_NOTHING_TO_SALVAGE`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
