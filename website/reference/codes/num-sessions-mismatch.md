---
description: "NUM_SESSIONS_MISMATCH: activity.num_sessions disagrees with actual session count. — what this chiptime warning code means and how to handle it."
---

# `NUM_SESSIONS_MISMATCH`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**activity.num_sessions disagrees with actual session count.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "NUM_SESSIONS_MISMATCH":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `NUM_SESSIONS_MISMATCH`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
