---
description: "RESYNC_SKIPPED_BYTES: Undecodable bytes skipped; decoding resumed at the next plausible definition frame. — what this chiptime provenance code means and how to handle it."
---

# `RESYNC_SKIPPED_BYTES`

> Generated from the code registries by `scripts/gen_code_pages.py` — do not hand-edit.

**Undecodable bytes skipped; decoding resumed at the next plausible definition frame.**

Provenance — a record of something chiptime *did* to your data (dropped, repaired, synthesized, reinterpreted, ignored). Appears in `provenance[]` with an `action`, a scope, and machine `data` — the never-lose-data-silently contract in practice.

## Proven by corpus cases

This code's behavior is pinned by committed conformance cases: [`protocol/frame-shift-insert`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/protocol/frame-shift-insert) · [`structural/garbage-block-midfile`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/structural/garbage-block-midfile) · [`structural/undefined-local-resync`](https://github.com/MaxGrgrv/chiptime/tree/main/corpus/cases/structural/undefined-local-resync)

## Handling it

```python
import chiptime

result = chiptime.parse("activity.fit")
for d in [*result.errors, *result.warnings, *result.provenance]:
    if d.code == "RESYNC_SKIPPED_BYTES":
        print(d.code, "-", d.detail)
```

All codes are stable machine contract — grep logs for the string `RESYNC_SKIPPED_BYTES`,
branch on it in pipelines, and see the [codes registry](index.md) for the
full list.
