---
description: "FIELD_RAW_SALVAGED: Field bytes undecodable as declared type; raw bytes kept. — what this chiptime provenance code means and how to handle it."
---

# `FIELD_RAW_SALVAGED`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Field bytes undecodable as declared type; raw bytes kept.**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`protocol/accumulator-rollover`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/protocol/accumulator-rollover) · [`protocol/compressed-speed-distance`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/protocol/compressed-speed-distance) · [`protocol/invalid-base-type`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/protocol/invalid-base-type) · [`sensors/hr-event-timestamp-12`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/sensors/hr-event-timestamp-12) · [`temporal/timestamp16-rollover`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/temporal/timestamp16-rollover)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "FIELD_RAW_SALVAGED":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `FIELD_RAW_SALVAGED`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
