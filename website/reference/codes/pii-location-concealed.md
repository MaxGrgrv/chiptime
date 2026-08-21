---
description: "PII_LOCATION_CONCEALED: GPS coordinates near the route endpoints were nulled at the user's request; they decode as absent, never as zero. — what this chiptime provenance code means and how to handle it."
---

# `PII_LOCATION_CONCEALED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**GPS coordinates near the route endpoints were nulled at the user's request; they decode as absent, never as zero.**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "PII_LOCATION_CONCEALED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `PII_LOCATION_CONCEALED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
