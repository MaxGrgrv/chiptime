---
description: "REPAIR_LOCAL_TIMESTAMP_DROPPED: Implausible local_timestamp not re-emitted (Zwift bug class, #37). — what this chiptime provenance code means and how to handle it."
---

# `REPAIR_LOCAL_TIMESTAMP_DROPPED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Implausible local_timestamp not re-emitted (Zwift bug class, #37).**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "REPAIR_LOCAL_TIMESTAMP_DROPPED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `REPAIR_LOCAL_TIMESTAMP_DROPPED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
