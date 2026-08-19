---
description: "FIT_HEADER_CRC_MISMATCH: Header CRC is wrong; continued. — what this chiptime warning code means and how to handle it."
---

# `FIT_HEADER_CRC_MISMATCH`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Header CRC is wrong; continued.**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`structural/header-crc-bad`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/structural/header-crc-bad) · [`structural/header-crc-bad`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/structural/header-crc-bad)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "FIT_HEADER_CRC_MISMATCH":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `FIT_HEADER_CRC_MISMATCH`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
