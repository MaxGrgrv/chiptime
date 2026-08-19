---
description: "TRUNCATED_TAIL_SALVAGED: File ends mid-content; complete records before the cut kept. — what this chiptime provenance code means and how to handle it."
---

# `TRUNCATED_TAIL_SALVAGED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**File ends mid-content; complete records before the cut kept.**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`structural/data-size-lies-short`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/structural/data-size-lies-short) · [`structural/truncated-mid-record`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/structural/truncated-mid-record)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "TRUNCATED_TAIL_SALVAGED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `TRUNCATED_TAIL_SALVAGED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
