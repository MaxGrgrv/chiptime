---
description: "ENHANCED_PAIR_DISAGREES: speed/altitude and their enhanced_ twins disagree; enhanced kept. — what this chiptime warning code means and how to handle it."
---

# `ENHANCED_PAIR_DISAGREES`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**speed/altitude and their enhanced_ twins disagree; enhanced kept.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`semantics/enhanced-pairs`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/semantics/enhanced-pairs)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "ENHANCED_PAIR_DISAGREES":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `ENHANCED_PAIR_DISAGREES`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
