---
description: "COASTING_HIGH: More than 25% of ride samples at 0 W — what this chiptime insight code means and how to handle it."
---

# `COASTING_HIGH`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**More than 25% of ride samples at 0 W**

Insight — a notable observation from the optional analytics layer (`chiptime analyze` / `chiptime.metrics.analyze`). Appears in a report's `insights[]` with a human message and numeric `evidence`.

## Handling it

```python
import chiptime
from chiptime import metrics

report = metrics.analyze(chiptime.parse("activity.fit"))
for ins in report.sessions[0].insights:
    if ins.code == "COASTING_HIGH":
        print(ins.message, ins.evidence)
```

All codes are stable machine contract — grep logs for the string `COASTING_HIGH`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
