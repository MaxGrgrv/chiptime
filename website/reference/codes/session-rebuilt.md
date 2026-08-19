---
description: "SESSION_REBUILT: No session message; session synthesized from records (#95). — what this chiptime provenance code means and how to handle it."
---

# `SESSION_REBUILT`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**No session message; session synthesized from records (#95).**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`devfields/dev-index-reused`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/devfields/dev-index-reused) · [`devfields/late-field-description`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/devfields/late-field-description) · [`devfields/missing-field-description`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/devfields/missing-field-description) · [`devfields/no-developer-data-id`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/devfields/no-developer-data-id) · [`devfields/null-field-name`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/devfields/null-field-name) · [`devfields/stryd-known-vendor`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/devfields/stryd-known-vendor)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "SESSION_REBUILT":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `SESSION_REBUILT`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
