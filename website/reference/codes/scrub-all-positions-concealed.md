---
description: "SCRUB_ALL_POSITIONS_CONCEALED: Every GPS point fell inside the concealment radius, so the scrubbed file has no route left at all. — what this chiptime warning code means and how to handle it."
---

# `SCRUB_ALL_POSITIONS_CONCEALED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Every GPS point fell inside the concealment radius, so the scrubbed file has no route left at all.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "SCRUB_ALL_POSITIONS_CONCEALED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `SCRUB_ALL_POSITIONS_CONCEALED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
