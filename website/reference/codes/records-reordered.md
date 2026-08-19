---
description: "RECORDS_REORDERED: Records were not in chronological order; stably sorted (ADR-0005 §1). — what this chiptime provenance code means and how to handle it."
---

# `RECORDS_REORDERED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Records were not in chronological order; stably sorted (ADR-0005 §1).**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`temporal/non-monotonic-records`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/temporal/non-monotonic-records)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "RECORDS_REORDERED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `RECORDS_REORDERED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
