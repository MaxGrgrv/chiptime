---
description: "PARTIAL_RECORD_DISCARDED: Trailing bytes formed an incomplete record; discarded. — what this chiptime provenance code means and how to handle it."
---

# `PARTIAL_RECORD_DISCARDED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Trailing bytes formed an incomplete record; discarded.**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "PARTIAL_RECORD_DISCARDED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `PARTIAL_RECORD_DISCARDED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
