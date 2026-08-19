---
description: "MOVEMENT_WITHOUT_DISTANCE: Speed present but distance never advances (#97). — what this chiptime warning code means and how to handle it."
---

# `MOVEMENT_WITHOUT_DISTANCE`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Speed present but distance never advances (#97).**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`multisport/triathlon`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/multisport/triathlon) · [`reconcile/zero-duration-lap`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/reconcile/zero-duration-lap) · [`reconcile/zero-duration-session`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/reconcile/zero-duration-session) · [`temporal/summary-first-layout`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/temporal/summary-first-layout) · [`temporal/zwift-local-timestamp-1989`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/temporal/zwift-local-timestamp-1989)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "MOVEMENT_WITHOUT_DISTANCE":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `MOVEMENT_WITHOUT_DISTANCE`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
