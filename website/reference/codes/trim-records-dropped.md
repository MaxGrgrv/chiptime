---
description: "TRIM_RECORDS_DROPPED: Records (and pool lengths) outside the requested trim window were removed at the user's explicit request. — what this chiptime provenance code means and how to handle it."
---

# `TRIM_RECORDS_DROPPED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Records (and pool lengths) outside the requested trim window were removed at the user's explicit request.**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "TRIM_RECORDS_DROPPED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `TRIM_RECORDS_DROPPED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
