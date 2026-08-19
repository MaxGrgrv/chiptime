---
description: "LAP_COVERAGE_GAP: Laps do not cover the session span (#94). — what this chiptime warning code means and how to handle it."
---

# `LAP_COVERAGE_GAP`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Laps do not cover the session span (#94).**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "LAP_COVERAGE_GAP":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `LAP_COVERAGE_GAP`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
