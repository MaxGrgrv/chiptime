---
description: The chiptime object model: ParseResult, Activity, Session, Records, Streams — the object tree and the ideas that organize it.
---

# Python API — model

What `parse` returns and what you drill into. Everything on this page is **plain
data** — frozen or simple dataclasses with no hidden state, no lazy IO, no
side effects. You make one call, then navigate attributes.

## The object tree

```text
ParseResult                         one parse() call returns exactly this
├─ ok · mode · file_type · source        the verdict + input identity
├─ errors · warnings · provenance        the paper trail (coded diagnostics)
├─ recovery                              what salvage did (None if unneeded)
├─ messages → [Message]                  lossless middle layer, file order
└─ activity → Activity                   the workout, made sense of
    ├─ sessions → [Session]              one per sport bout
    │   ├─ declared / derived → Totals   device's claim vs recomputed truth
    │   ├─ discrepancies                 where those two disagree
    │   ├─ laps · lengths                declared structure
    │   └─ records → Records             the per-second timeline
    │       └─ streams → {Stream}        columnar; null ≠ 0, always
    ├─ gaps                              recording holes, classified
    └─ events · device · athlete · hrv_intervals_s
```

Three ideas organize it:

1. **Two truths, kept side by side.** Devices declare totals; chiptime recomputes
   them from the records. `Session.declared` and `Session.derived` are both
   `Totals`, and `discrepancies` lists every material disagreement — the
   disagreement is signal, not noise to reconcile away.
2. **Columns, not rows.** `Records` stores one shared time axis plus one `Stream`
   per field. That makes analytics natural (a stream is already a series) and
   keeps unknown fields lossless — every field any record carried becomes a
   stream, known or not.
3. **The paper trail is part of the result.** `provenance` on `ParseResult` is
   the complete list of decisions chiptime made about your data. An empty list
   means the file was exactly what it claimed to be.

## The result envelope

::: chiptime.result.ParseResult

::: chiptime.result.RecoveryReport

::: chiptime.result.SourceInfo

## The workout model

`Activity` is the semantic view of one activity part; `Session` is the unit
almost everything operates on — analytics functions take a `Session`, splits and
intervals are computed per session, and multisport files simply have several.

::: chiptime.model.Activity

::: chiptime.model.Session

::: chiptime.model.Totals

::: chiptime.model.Records

::: chiptime.model.Stream

::: chiptime.model.Lap

::: chiptime.model.Length

::: chiptime.model.Gap

::: chiptime.model.Discrepancy

## Messages — the lossless middle layer

Below the workout model sits the decoded message list: every message in file
order, unknown-tolerant, with both decoded values and raw wire values. The
semantic model is *derived* from these; nothing is lost in between. Analytics
functions accept `result.messages` to read fields the semantic model doesn't
surface (lap triggers, workout steps, pool length).

::: chiptime.message.Message

::: chiptime.message.FieldValue

## Repair and validation results

::: chiptime.repair.RepairResult

::: chiptime.validate.Finding
