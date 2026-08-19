---
description: "REPAIR_ACTIVITY_SYNTHESIZED: Repair synthesized the activity message (#96). — what this chiptime provenance code means and how to handle it."
---

# `REPAIR_ACTIVITY_SYNTHESIZED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Repair synthesized the activity message (#96).**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "REPAIR_ACTIVITY_SYNTHESIZED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `REPAIR_ACTIVITY_SYNTHESIZED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
