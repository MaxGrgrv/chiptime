---
description: "DEV_FIELD_NAME_SYNTHESIZED: Developer field lacked usable metadata; name synthesized, data kept. — what this chiptime warning code means and how to handle it."
---

# `DEV_FIELD_NAME_SYNTHESIZED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Developer field lacked usable metadata; name synthesized, data kept.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`devfields/late-field-description`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/devfields/late-field-description) · [`devfields/missing-field-description`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/devfields/missing-field-description) · [`devfields/null-field-name`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/devfields/null-field-name)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "DEV_FIELD_NAME_SYNTHESIZED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `DEV_FIELD_NAME_SYNTHESIZED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
