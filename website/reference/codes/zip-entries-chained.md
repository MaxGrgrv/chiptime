---
description: "ZIP_ENTRIES_CHAINED: Multiple .fit entries in a zip parsed as chained parts. — what this chiptime provenance code means and how to handle it."
---

# `ZIP_ENTRIES_CHAINED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Multiple .fit entries in a zip parsed as chained parts.**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "ZIP_ENTRIES_CHAINED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `ZIP_ENTRIES_CHAINED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
