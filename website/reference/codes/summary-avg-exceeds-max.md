---
description: "SUMMARY_AVG_EXCEEDS_MAX: A declared average exceeds its declared maximum (#93). — what this chiptime warning code means and how to handle it."
---

# `SUMMARY_AVG_EXCEEDS_MAX`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**A declared average exceeds its declared maximum (#93).**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`reconcile/summary-mismatch`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/reconcile/summary-mismatch)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "SUMMARY_AVG_EXCEEDS_MAX":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `SUMMARY_AVG_EXCEEDS_MAX`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
