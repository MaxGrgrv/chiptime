---
description: "STREAM_STOPPED_AT_DEFECT: Decoding stopped at a structural defect; prefix salvaged. — what this chiptime provenance code means and how to handle it."
---

# `STREAM_STOPPED_AT_DEFECT`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Decoding stopped at a structural defect; prefix salvaged.**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`structural/garbage-block-midfile`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/structural/garbage-block-midfile)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "STREAM_STOPPED_AT_DEFECT":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `STREAM_STOPPED_AT_DEFECT`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
