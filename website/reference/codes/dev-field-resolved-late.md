---
description: "DEV_FIELD_RESOLVED_LATE: Developer fields re-resolved after their field_description arrived later in the file. — what this chiptime provenance code means and how to handle it."
---

# `DEV_FIELD_RESOLVED_LATE`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Developer fields re-resolved after their field_description arrived later in the file.**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`devfields/late-field-description`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/devfields/late-field-description)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "DEV_FIELD_RESOLVED_LATE":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `DEV_FIELD_RESOLVED_LATE`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
