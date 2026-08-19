---
description: "VIRTUAL_GPS_EXEMPT: Virtual-world coordinates exempt from plausibility gating (#57). — what this chiptime provenance code means and how to handle it."
---

# `VIRTUAL_GPS_EXEMPT`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Virtual-world coordinates exempt from plausibility gating (#57).**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`gps/virtual-gps-zwift`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/gps/virtual-gps-zwift)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "VIRTUAL_GPS_EXEMPT":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `VIRTUAL_GPS_EXEMPT`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
