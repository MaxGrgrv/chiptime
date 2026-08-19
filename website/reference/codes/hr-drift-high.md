---
description: "HR_DRIFT_HIGH: Speed/power per heartbeat fell >5% first half to second (aerobic decoupling) — what this chiptime insight code means and how to handle it."
---

# `HR_DRIFT_HIGH`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Speed/power per heartbeat fell >5% first half to second (aerobic decoupling)**

Insight — a notable observation from the optional analytics layer (`chiptime analyze` / `chiptime.metrics.analyze`). Appears in a report's `insights[]` with a human message and numeric `evidence`.

## Handling it

```python
import chiptime
from chiptime import metrics

report = metrics.analyze(chiptime.parse("activity.fit"))
for ins in report.sessions[0].insights:
    if ins.code == "HR_DRIFT_HIGH":
        print(ins.message, ins.evidence)
```

All codes are stable machine contract — grep logs for the string `HR_DRIFT_HIGH`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
