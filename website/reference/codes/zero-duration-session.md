---
description: "ZERO_DURATION_SESSION: Session declares zero duration but contains records (#97). — what this chiptime warning code means and how to handle it."
---

# `ZERO_DURATION_SESSION`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Session declares zero duration but contains records (#97).**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`reconcile/zero-duration-session`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/reconcile/zero-duration-session)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "ZERO_DURATION_SESSION":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `ZERO_DURATION_SESSION`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
