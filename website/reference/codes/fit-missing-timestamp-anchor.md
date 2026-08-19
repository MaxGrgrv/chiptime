---
description: "FIT_MISSING_TIMESTAMP_ANCHOR: Compressed timestamps had no anchor; those stamps absent. — what this chiptime warning code means and how to handle it."
---

# `FIT_MISSING_TIMESTAMP_ANCHOR`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Compressed timestamps had no anchor; those stamps absent.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "FIT_MISSING_TIMESTAMP_ANCHOR":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `FIT_MISSING_TIMESTAMP_ANCHOR`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
