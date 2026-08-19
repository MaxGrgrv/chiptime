---
description: "ENHANCED_PAIR_MERGED: enhanced_speed/altitude merged into the base stream (enhanced preferred, taxonomy #28). — what this chiptime provenance code means and how to handle it."
---

# `ENHANCED_PAIR_MERGED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**enhanced_speed/altitude merged into the base stream (enhanced preferred, taxonomy #28).**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`semantics/enhanced-pairs`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/semantics/enhanced-pairs)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "ENHANCED_PAIR_MERGED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `ENHANCED_PAIR_MERGED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
