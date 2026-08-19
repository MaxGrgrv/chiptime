---
description: "RELATIVE_TIMESTAMP: A date_time value is device-relative (< 0x10000000), not absolute. — what this chiptime warning code means and how to handle it."
---

# `RELATIVE_TIMESTAMP`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**A date_time value is device-relative (< 0x10000000), not absolute.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`temporal/system-time-only`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/temporal/system-time-only) · [`temporal/zwift-local-timestamp-1989`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/temporal/zwift-local-timestamp-1989)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "RELATIVE_TIMESTAMP":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `RELATIVE_TIMESTAMP`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
