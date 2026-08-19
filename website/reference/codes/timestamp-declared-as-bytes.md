---
description: "TIMESTAMP_DECLARED_AS_BYTES: Field 253 declared as byte[4]; reassembled (Xiaomi-pipeline class). — what this chiptime warning code means and how to handle it."
---

# `TIMESTAMP_DECLARED_AS_BYTES`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Field 253 declared as byte[4]; reassembled (Xiaomi-pipeline class).**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`temporal/timestamp-as-bytes`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/temporal/timestamp-as-bytes)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "TIMESTAMP_DECLARED_AS_BYTES":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `TIMESTAMP_DECLARED_AS_BYTES`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
