---
description: "WORKOUT_STRUCTURE: Repeated interval structure found (label in evidence) — what this chiptime insight code means and how to handle it."
---

# `WORKOUT_STRUCTURE`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Repeated interval structure found (label in evidence)**

Insight — a notable observation from the optional analytics layer (`chiptime analyze` / `chiptime.metrics.analyze`). Appears in a report's `insights[]` with a human message and numeric `evidence`.

## Handling it

```python
import chiptime
from chiptime import metrics

report = metrics.analyze(chiptime.parse("activity.fit"))
for ins in report.sessions[0].insights:
    if ins.code == "WORKOUT_STRUCTURE":
        print(ins.message, ins.evidence)
```

All codes are stable machine contract — grep logs for the string `WORKOUT_STRUCTURE`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
