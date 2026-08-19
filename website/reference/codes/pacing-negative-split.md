---
description: "PACING_NEGATIVE_SPLIT: Second half faster than the first by more than 2% — what this chiptime insight code means and how to handle it."
---

# `PACING_NEGATIVE_SPLIT`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Second half faster than the first by more than 2%**

Insight — a notable observation from the optional analytics layer (`chiptime analyze` / `chiptime.metrics.analyze`). Appears in a report's `insights[]` with a human message and numeric `evidence`.

## Handling it

```python
import chiptime
from chiptime import metrics

report = metrics.analyze(chiptime.parse("activity.fit"))
for ins in report.sessions[0].insights:
    if ins.code == "PACING_NEGATIVE_SPLIT":
        print(ins.message, ins.evidence)
```

All codes are stable machine contract — grep logs for the string `PACING_NEGATIVE_SPLIT`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
