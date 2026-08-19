---
description: "NULL_ISLAND_DROPPED: Records at exactly (0,0) nulled or flagged (#51). — what this chiptime provenance code means and how to handle it."
---

# `NULL_ISLAND_DROPPED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Records at exactly (0,0) nulled or flagged (#51).**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`gps/null-island`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/gps/null-island)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "NULL_ISLAND_DROPPED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `NULL_ISLAND_DROPPED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
