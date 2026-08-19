---
description: "FIT_TRAILING_JUNK: Bytes after the final CRC are not a chained FIT file; ignored. — what this chiptime warning code means and how to handle it."
---

# `FIT_TRAILING_JUNK`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Bytes after the final CRC are not a chained FIT file; ignored.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`structural/trailing-junk`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/structural/trailing-junk) · [`structural/trailing-junk`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/structural/trailing-junk)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "FIT_TRAILING_JUNK":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `FIT_TRAILING_JUNK`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
