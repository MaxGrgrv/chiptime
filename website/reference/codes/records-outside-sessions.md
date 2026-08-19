---
description: "RECORDS_OUTSIDE_SESSIONS: Records fall outside every session's bounds; attached to nearest. — what this chiptime warning code means and how to handle it."
---

# `RECORDS_OUTSIDE_SESSIONS`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Records fall outside every session's bounds; attached to nearest.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "RECORDS_OUTSIDE_SESSIONS":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `RECORDS_OUTSIDE_SESSIONS`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
