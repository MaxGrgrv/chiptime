---
description: "FIT_CRC_MISSING: File CRC trailer absent; content used as-is. — what this chiptime warning code means and how to handle it."
---

# `FIT_CRC_MISSING`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**File CRC trailer absent; content used as-is.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "FIT_CRC_MISSING":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `FIT_CRC_MISSING`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
