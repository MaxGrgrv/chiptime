---
description: "FIT_EMPTY: The file contains no bytes. — what this chiptime error code means and how to handle it."
---

# `FIT_EMPTY`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**The file contains no bytes.**

Error — the file violates the FIT structure this code names. In `lenient`/`forensic` mode it lands in `errors[]` on the result; in `strict` mode it raises a `chiptime.FitError` subclass carrying this code, a human `detail`, and (where useful) a `suggestion`.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`structural/empty-file`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/structural/empty-file)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "FIT_EMPTY":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `FIT_EMPTY`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
