---
description: "TRIM_SUMMARIES_REBUILT: Session and activity totals were recomputed from the records that survived a trim, so the file cannot carry stale summaries. — what this chiptime provenance code means and how to handle it."
---

# `TRIM_SUMMARIES_REBUILT`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Session and activity totals were recomputed from the records that survived a trim, so the file cannot carry stale summaries.**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "TRIM_SUMMARIES_REBUILT":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `TRIM_SUMMARIES_REBUILT`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
