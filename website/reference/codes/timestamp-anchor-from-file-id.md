---
description: "TIMESTAMP_ANCHOR_FROM_FILE_ID: Compressed timestamps anchored from file_id.time_created. — what this chiptime provenance code means and how to handle it."
---

# `TIMESTAMP_ANCHOR_FROM_FILE_ID`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Compressed timestamps anchored from file_id.time_created.**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "TIMESTAMP_ANCHOR_FROM_FILE_ID":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `TIMESTAMP_ANCHOR_FROM_FILE_ID`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
