# ADR-0006: Encoder policy — canonical wire form, two producers

> Status: ACCEPTED · 2026-08-18 · Feature: F12

## Context
M2's repair pipeline must emit valid .fit files (research gap #2: no OSS path
from salvage to a conformant file). fit-tool proves lossless *editing* is its
own discipline (PRESERVE mode); repair needs something simpler and stricter.

## Decisions
1. **Canonical wire form only**: little-endian, 14-byte header (computed header
   CRC), definitions emitted on shape change, no compressed-timestamp headers,
   file CRC always recomputed. We do not reproduce the input's wire quirks —
   repair output is *clean by construction* (bit-preserving round-trip is a
   non-goal; that's forensio/fit-tool territory).
2. **One encoder, two producers** of `EncodableMessage(global_num, specs)`:
   - `encodable_from_message(msg)`: losslessly re-emit a decoded message from
     its retained wire definition + raw values — unknown messages and unknown
     fields included. Timestamps derived from compressed headers are
     materialized as explicit field 253 (the wire definition is extended).
   - `encodable_from_profile(num, values)`: synthesize messages (repair's
     session/activity/events) from the profile — names → field numbers, values
     reverse-scaled (`raw = round((value + offset) * scale)`), enums by name,
     ISO datetimes → FIT seconds.
3. **Local slot management**: shape-keyed (global + field specs + dev specs)
   with a deterministic round-robin over the 16 slots; redefinition on
   eviction. Same input → byte-identical output (encoder determinism is
   corpus-testable).
4. **Messages carry their wire definition** (`Message.wire`) from decode on —
   round-trips need the authoritative field widths, and forensics benefit.
5. **Round-trip contract** (test-enforced): `parse(encode(parse(x).messages))`
   is semantically identical to `parse(x)` — canonical dicts equal after
   stripping `source` and byte offsets — and re-encoded files pass **strict**
   parsing (spec-clean output or bust).

## Consequences
- Repair output may be byte-different from any device file (clean form) —
  platform acceptance relies on structural validity (F14 validates), not
  byte mimicry.
- Developer fields re-encode naturally: their metadata messages travel in the
  same message list.
