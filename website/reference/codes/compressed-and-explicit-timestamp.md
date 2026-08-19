---
description: "COMPRESSED_AND_EXPLICIT_TIMESTAMP: Record had both timestamp forms; explicit kept. — what this chiptime warning code means and how to handle it."
---

# `COMPRESSED_AND_EXPLICIT_TIMESTAMP`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Record had both timestamp forms; explicit kept.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "COMPRESSED_AND_EXPLICIT_TIMESTAMP":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `COMPRESSED_AND_EXPLICIT_TIMESTAMP`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
