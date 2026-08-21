---
description: "ACTIVITY_MESSAGE_MISSING: No activity message present (#96); repair can synthesize. — what this chiptime warning code means and how to handle it."
---

# `ACTIVITY_MESSAGE_MISSING`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**No activity message present (#96); repair can synthesize.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`gps/spike-bounce`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/gps/spike-bounce) · [`gps/treadmill-final-jump`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/gps/treadmill-final-jump) · [`protocol/unknown-enum-values`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/protocol/unknown-enum-values) · [`reconcile/summary-mismatch`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/reconcile/summary-mismatch) · [`reconcile/zero-duration-lap`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/reconcile/zero-duration-lap) · [`reconcile/zero-duration-session`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/reconcile/zero-duration-session)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "ACTIVITY_MESSAGE_MISSING":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `ACTIVITY_MESSAGE_MISSING`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
