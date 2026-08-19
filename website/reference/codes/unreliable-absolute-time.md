---
description: "UNRELIABLE_ABSOLUTE_TIME: Timestamps predate 2010; device likely never got GPS time. Relative timeline kept. — what this chiptime warning code means and how to handle it."
---

# `UNRELIABLE_ABSOLUTE_TIME`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Timestamps predate 2010; device likely never got GPS time. Relative timeline kept.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`temporal/pre-2010-timestamps`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/temporal/pre-2010-timestamps)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "UNRELIABLE_ABSOLUTE_TIME":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `UNRELIABLE_ABSOLUTE_TIME`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
