---
description: "POOL_ZERO_LENGTH: Active pool lengths under 2 s; push-off artifacts (#73). — what this chiptime warning code means and how to handle it."
---

# `POOL_ZERO_LENGTH`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Active pool lengths under 2 s; push-off artifacts (#73).**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`swim/pool-lengths`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/swim/pool-lengths)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "POOL_ZERO_LENGTH":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `POOL_ZERO_LENGTH`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
