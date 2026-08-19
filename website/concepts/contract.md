---
description: The eight invariants behind chiptime: never lose data silently, byte-deterministic output, zero is not null, honest non-recovery.
---

# The contract

Eight invariants govern every feature. They are enforced in review and CI — a change
that violates one does not ship.

## 1. Never lose data silently

Every drop, repair, and reinterpretation lands in `provenance[]` on the output, with
a machine code and a human sentence. If chiptime touched your data, the record says
where, what, and why.

## 2. Deterministic

Same input bytes → byte-identical canonical JSON, across runs, processes, and
operating systems. No wall-clock, no randomness, no dict-ordering luck.
[More →](determinism.md)

## 3. Three modes, one switch

`strict` (spec lawyer, fail fast) · `lenient` (default: recover and warn) ·
`forensic` (maximum salvage, everything annotated). One policy switch — not three
codepaths that drift apart.

## 4. Sentinels → null before any statistics — and zero ≠ null, always

`0xFF` heart rate, `0xFFFF` power, `0x7FFFFFFF` semicircles are *absence*, converted
to `null` at decode time. Coasting is 0 W (real); dropout is `null` (absent). No
average, curve, or zone calculation ever sees a sentinel.

## 5. Errors are written for agents

Machine-parseable `code` + human `detail` + `suggestion` (often the exact flag to
retry with). Exit codes route control flow without parsing prose.

## 6. Unknown ≠ invalid

Unknown messages, fields, and enum values are preserved with raw values — never a
crash. Forward-compatible with devices that don't exist yet.

## 7. Every taxonomy item → a corpus case

All 104 documented edge cases map to committed conformance cases with expected
outputs. Claims about behavior are tests, not prose.

## 8. Honest non-recovery

Report what is genuinely absent; never fabricate. A repaired file is an honest
shorter ride, not an imagined complete one. The analytics layer extends this upward:
thresholds and zones are never estimated from the workout itself.
