---
description: "STRING_DECODE_REPLACED: A string field contained invalid UTF-8; replacements used. — what this chiptime warning code means and how to handle it."
---

# `STRING_DECODE_REPLACED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**A string field contained invalid UTF-8; replacements used.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`protocol/string-edges`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/protocol/string-edges)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "STRING_DECODE_REPLACED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `STRING_DECODE_REPLACED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
