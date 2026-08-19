---
description: "NOT_FIT_FORMAT: The content is not FIT (detail names what it looks like). — what this chiptime error code means and how to handle it."
---

# `NOT_FIT_FORMAT`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**The content is not FIT (detail names what it looks like).**

Error — the file violates the FIT structure this code names. In `lenient`/`forensic` mode it lands in `errors[]` on the result; in `strict` mode it raises a `chiptime.FitError` subclass carrying this code, a human `detail`, and (where useful) a `suggestion`.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`container/gpx-renamed`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/container/gpx-renamed) · [`container/html-error-page`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/container/html-error-page) · [`container/json-error`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/container/json-error) · [`container/tcx-renamed`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/container/tcx-renamed)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "NOT_FIT_FORMAT":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `NOT_FIT_FORMAT`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
