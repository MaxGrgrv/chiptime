---
description: "HR_EXPANSION_NO_ANCHOR: hr.event_timestamp_12 appeared before any full event_timestamp; samples not expandable. — what this chiptime warning code means and how to handle it."
---

# `HR_EXPANSION_NO_ANCHOR`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**hr.event_timestamp_12 appeared before any full event_timestamp; samples not expandable.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "HR_EXPANSION_NO_ANCHOR":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `HR_EXPANSION_NO_ANCHOR`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
