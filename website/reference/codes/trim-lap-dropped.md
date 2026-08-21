---
description: "TRIM_LAP_DROPPED: A lap not wholly inside the trim window was removed; its in-window records were kept. — what this chiptime provenance code means and how to handle it."
---

# `TRIM_LAP_DROPPED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**A lap not wholly inside the trim window was removed; its in-window records were kept.**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "TRIM_LAP_DROPPED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `TRIM_LAP_DROPPED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
