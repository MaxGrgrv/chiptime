---
description: The 104-item FIT edge-case taxonomy chiptime is built against: timestamp pathologies, sentinel traps, vendor quirks, corruption.
---

# The edge-case taxonomy

chiptime began as a catalog before it was code: **104 documented ways FIT files go
wrong in the real world**, organized into tiers — truncation and corruption,
timestamp pathologies, sentinel and encoding traps, vendor quirks, multisport
structure, developer fields, GPS implausibility, and more.

The taxonomy is the parser-behavior backlog: every item maps to at least one
[conformance corpus case](../guides/corpus.md) with a committed expected output.
A behavior isn't "handled" until its case is green.

## A taste

| Item | The trap | chiptime's behavior |
|---|---|---|
| Zwift 1989 timestamps | Trainer writes `local_timestamp` before the FIT epoch | Reinterpreted with provenance; repair drops the field platforms reject |
| 12-bit HR event timestamps | `event_timestamp_12` packs 12-bit values across bytes | Expanded correctly, 12-bit rollover included |
| Sentinel HR/power | `0xFF` / `0xFFFF` are "no reading", not values | `null` before any statistics — never a 65,535 W sprint |
| Per-leg run cadence | Devices write strides/min of one leg | Doubled only for display, labeled `doubled_per_leg_cadence` |
| Pool zero-length | Watches log phantom 0 s lengths at the wall | Flagged, excluded from sets, kept in output |
| Chained files | Multiple FIT parts concatenated | Each part parsed, reported separately |

The full document lives in the repository:
[`docs/edge-case-taxonomy.md`](https://github.com/MaxGrgrv/chiptime/blob/main/docs/edge-case-taxonomy.md).
