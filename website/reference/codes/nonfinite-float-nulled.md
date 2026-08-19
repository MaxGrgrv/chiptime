---
description: "NONFINITE_FLOAT_NULLED: A float field carried NaN/Infinity; treated as absent. — what this chiptime warning code means and how to handle it."
---

# `NONFINITE_FLOAT_NULLED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**A float field carried NaN/Infinity; treated as absent.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`protocol/float-nan-inf`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/protocol/float-nan-inf) · [`protocol/float-sentinel-vs-nan`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/protocol/float-sentinel-vs-nan)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "NONFINITE_FLOAT_NULLED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `NONFINITE_FLOAT_NULLED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
