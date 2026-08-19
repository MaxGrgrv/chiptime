# ADR-0003: Defects as values; modes as policy at the API boundary

> Status: ACCEPTED · 2026-08-17 · Feature: F3

## Context
Recovery (resync, salvage) is impossible if the decode pipeline throws exceptions: an exception unwinds the state (local message table, timestamp anchor) that recovery needs. Existing parsers prove this — every thrower loses everything past the first bad byte (research §6.1).

## Decision
1. The frame reader and decoder **never raise on content**. Every problem becomes a `Defect` value (code, detail, byte offset, severity) emitted in-stream alongside frames.
2. Severity taxonomy: `fatal` (no usable stream possible: not FIT at all, empty), `structural` (framing damage: truncation, bad definition, undefined local type), `data` (field-level: invalid base type, bad UTF-8, NaN).
3. **Modes are one policy switch applied at the API boundary** (`_api.parse`), not separate code paths:
   - `strict`: first Defect of any severity → raise its mapped `FitError`. (Spec-lawyer: even a CRC mismatch with perfect data raises.)
   - `lenient` (default): Defects drive recovery (F5); repaired/skipped things land in `provenance[]`, non-fatal issues in `warnings[]`, unusable-input in `errors[]`; plausibility gates may *drop* data (always with provenance).
   - `forensic`: like lenient, but **never drops** — plausibility findings only annotate; salvaged partial data is retained as raw annotated entries where lenient would discard.
4. One decode implementation, three read-outs. Divergence between modes must be expressible as policy checks (`if policy.drops_implausible: ...`), never as duplicated decode logic.

## Consequences
- `strict` costs one branch per defect — no performance or duplication tax.
- Recovery state (local table, anchors) survives any defect by construction.
- Every Defect must carry a byte offset — enforced by the dataclass; "somewhere in the file" errors are structurally impossible.
