---
description: chiptime Python API entry points: parse, iter_messages, iter_frames, repair, validate — one call, then navigate plain data.
---

# Python API — core

Five entry points, one mental model: **make one call, then navigate the result**
([the object tree](api-model.md#the-object-tree)). There are no sessions to
open, no configuration objects, no state to manage — every function is
input → complete result.

## Which entry point?

| You want | Call |
|---|---|
| The workout, fully interpreted | `parse` — the main call, 99% of uses |
| To stream a huge file in constant memory | `iter_messages` |
| Wire-level bytes forensics | `iter_frames` |
| A broken file made uploadable | `repair` |
| Metadata changed (sport, device, clock) | `edit` |
| An activity cropped, totals rebuilt | `trim` |
| To know what a file discloses | `reveal` |
| Personal data removed before sharing | `scrub` |
| "Will this platform accept it?" | `validate` |

`parse` reads everything into a `ParseResult`; the iterators yield as they go
and skip the semantic layer entirely. `repair` and `validate` are built *on*
`parse` — they see exactly what it sees.

## Parse

::: chiptime.parse

## Stream without the semantic layer

::: chiptime.iter_messages

::: chiptime.iter_frames

## Repair

::: chiptime.repair

## Edit

::: chiptime.edit

::: chiptime.edit.EditResult

## Trim

::: chiptime.trim

::: chiptime.trim.TrimResult

## Privacy

::: chiptime.reveal

::: chiptime.scrub

::: chiptime.privacy.PrivacyReport

::: chiptime.privacy.ScrubResult

## Validate

::: chiptime.validate.validate
