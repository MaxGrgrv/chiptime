---
description: "FIT_HEADER_INVALID: Header is nonstandard; continued on best interpretation. — what this chiptime warning code means and how to handle it."
---

# `FIT_HEADER_INVALID`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Header is nonstandard; continued on best interpretation.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`structural/header-size-invalid`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/structural/header-size-invalid) · [`structural/header-size-invalid`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/structural/header-size-invalid) · [`structural/magic-missing`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/structural/magic-missing) · [`structural/magic-missing`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/structural/magic-missing)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "FIT_HEADER_INVALID":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `FIT_HEADER_INVALID`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
