---
description: "FIT_DATA_SIZE_MISMATCH: Header data_size is wrong; trusting actual content. — what this chiptime warning code means and how to handle it."
---

# `FIT_DATA_SIZE_MISMATCH`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Header data_size is wrong; trusting actual content.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "FIT_DATA_SIZE_MISMATCH":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `FIT_DATA_SIZE_MISMATCH`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
