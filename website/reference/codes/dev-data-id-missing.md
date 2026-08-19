---
description: "DEV_DATA_ID_MISSING: field_description references a developer_data_index that was never announced. — what this chiptime warning code means and how to handle it."
---

# `DEV_DATA_ID_MISSING`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**field_description references a developer_data_index that was never announced.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`devfields/no-developer-data-id`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/devfields/no-developer-data-id)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "DEV_DATA_ID_MISSING":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `DEV_DATA_ID_MISSING`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
