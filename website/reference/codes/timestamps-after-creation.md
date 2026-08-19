---
description: "TIMESTAMPS_AFTER_CREATION: Records postdate file_id.time_created by more than 7 days; device clock suspect. — what this chiptime warning code means and how to handle it."
---

# `TIMESTAMPS_AFTER_CREATION`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Records postdate file_id.time_created by more than 7 days; device clock suspect.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "TIMESTAMPS_AFTER_CREATION":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `TIMESTAMPS_AFTER_CREATION`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
