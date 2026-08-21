---
description: "DISTANCE_RESCALED_PAIR: Distance was rescaled; speed was scaled by the same factor so the stream stays internally consistent. — what this chiptime warning code means and how to handle it."
---

# `DISTANCE_RESCALED_PAIR`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Distance was rescaled; speed was scaled by the same factor so the stream stays internally consistent.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "DISTANCE_RESCALED_PAIR":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `DISTANCE_RESCALED_PAIR`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
