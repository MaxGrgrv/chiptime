---
description: "SUMMARY_NEGATIVE_TOTAL: A declared total is negative (#93). — what this chiptime warning code means and how to handle it."
---

# `SUMMARY_NEGATIVE_TOTAL`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**A declared total is negative (#93).**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "SUMMARY_NEGATIVE_TOTAL":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `SUMMARY_NEGATIVE_TOTAL`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
