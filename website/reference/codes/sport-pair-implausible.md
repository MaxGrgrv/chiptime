---
description: "SPORT_PAIR_IMPLAUSIBLE: Sport was edited while a non-generic sub-sport was left in place; verify the pair is what you intended (chiptime never guesses a replacement). — what this chiptime warning code means and how to handle it."
---

# `SPORT_PAIR_IMPLAUSIBLE`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Sport was edited while a non-generic sub-sport was left in place; verify the pair is what you intended (chiptime never guesses a replacement).**

Warning — chiptime saw something suspicious, handled it, and continued. Appears in `warnings[]` on the result in every mode.

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "SPORT_PAIR_IMPLAUSIBLE":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `SPORT_PAIR_IMPLAUSIBLE`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
