---
description: "DISTANCE_RESCALED: Recorded distance (and speed) scaled to a user-supplied total, with summaries updated so records and totals still agree. — what this chiptime provenance code means and how to handle it."
---

# `DISTANCE_RESCALED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Recorded distance (and speed) scaled to a user-supplied total, with summaries updated so records and totals still agree.**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "DISTANCE_RESCALED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `DISTANCE_RESCALED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
