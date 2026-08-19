---
description: "DEV_INDEX_REDEFINED: A developer_data_index was redefined mid-file by another app. — what this chiptime warning code means and how to handle it."
---

# `DEV_INDEX_REDEFINED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**A developer_data_index was redefined mid-file by another app.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`devfields/dev-index-reused`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/devfields/dev-index-reused)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "DEV_INDEX_REDEFINED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `DEV_INDEX_REDEFINED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
