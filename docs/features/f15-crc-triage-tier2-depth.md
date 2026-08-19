# Feature: F15 — CRC Triage + Tier-2 Depth Batch

> Status: DONE

## Purpose
The Tier-2 fast-follow batch: diagnose *why* a CRC fails (#4 depth — research gap #8), expand legacy component fields (#29), unwrap accumulators (#30), resolve event subfields (#31), flag distance anomalies (#59) and physiologically impossible HR/power (#62/#63, flags only), pool-length semantics (#73), zero-duration laps + lap coverage (#94).

## Taxonomy Coverage
| # | Summary | Corpus case |
|---|---|---|
| 4 (depth) | CRC triage: unterminated-write vs in-place corruption | structural/file-crc-zeroed |
| 29 | compressed_speed_distance expansion, 12-bit distance rollover | protocol/compressed-speed-distance |
| 30 | Accumulated-field wrap detection | protocol/accumulator-rollover |
| 31 | event.data subfield resolution (timer_trigger) | protocol/event-subfields |
| 59 | Distance decreasing/reset/frozen | sensors/distance-anomalies |
| 62/63 | HR/power implausibility + flatline — flags, never edits | sensors/hr-power-implausible |
| 73 | Pool lengths: count×size vs declared, zero-length artifacts | swim/pool-lengths |
| 94 | Zero-duration laps, lap coverage gaps | reconcile/zero-duration-lap |

## Requirements
1. CRC triage in the frame reader: zeroed trailer → "unterminated write"; clean-decode mismatch → "in-place corruption or lazy encoder CRC" (fitparse #9 class); detail carries the class.
2. Decode-layer expansion (deterministic, stateful): compressed_speed_distance → speed + accumulated distance (12-bit modular delta); accumulated_power unwrapped on wrap (provenance, aggregated).
3. Subfields: `event.data` resolved per event type (timer → `timer_trigger`), original field retained.
4. Sensor flags (reconcile/plausibility, flags only — interpolation stays BACKLOG): HR > 230 or ≥ 120 s flatline; power > 2500 W; distance decreasing / reset-to-zero / frozen-while-moving.
5. Swim: active-length count × pool_length vs declared distance (mis-set pool size is *flaggable, not fixable* — taxonomy's own words); zero-length artifacts.
6. Laps: zero-duration warning; coverage gap warning when laps span < 90% of records span.

## Critique & Assessment
- **Alternatives considered:** auto-dropping implausible HR/power (rejected — taxonomy #62 makes interpolation an opt-in repair; flags preserve analytics choice); full component-field generality (rejected — csd is the only Tier-2 component; generic machinery when a second one lands).
- **Contract check:** expansions/unwraps → provenance; all sensor findings are warnings; zero mutations outside csd/accumulator expansion (which are decodes, not edits).
- **Final decision:** APPROVE

## Dependencies
- **Depends on:** F7–F10 · **Depended on by:** F16

## Related
- Implementation: [../implementation/f15-crc-triage-tier2-depth.md](../implementation/f15-crc-triage-tier2-depth.md)
