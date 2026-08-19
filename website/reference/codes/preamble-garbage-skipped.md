---
description: "PREAMBLE_GARBAGE_SKIPPED: Garbage before the FIT header skipped; header re-anchored. — what this chiptime provenance code means and how to handle it."
---

# `PREAMBLE_GARBAGE_SKIPPED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Garbage before the FIT header skipped; header re-anchored.**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`structural/preamble-garbage`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/structural/preamble-garbage)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "PREAMBLE_GARBAGE_SKIPPED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `PREAMBLE_GARBAGE_SKIPPED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
