# Feature: F38 — Encoder, `repair`, `validate` for TypeScript → npm `0.2.0`

> Status: DONE
>
> Lifecycle note: like F37, no separate `/critique` pass — the surface is a port of
> already-critiqued contracts (F12–F14) and the gate is exhaustive: every corpus case
> through `repair` (output **file bytes** compared) and all three `validate` platforms.

## Purpose
`encode.ts` (canonical wire form, ADR-0006), `repair.ts` (salvage → synthesize → valid
.fit, honest refusal per contract #8), `validate.ts` (strict-spec / garmin-connect /
strava). CLI gains `repair` and `validate`. Surface = PyPI `0.2.0`.

## Gate
`check_cli_parity.py` grew from 507 to **795 invocations**: `repair -o` (stdout, exit
code, AND the repaired file's bytes), `validate` × 3 platforms, across all 72 cases.
Repaired outputs are byte-identical to Python's — the encoder, slot allocator, profile
synthesis and pyRound'd summary values all agree, proven at the wire level.

## Notes
- `_Slots` 16-slot rotation ported with a string shape key standing in for Python's
  tuple key; byte-identical outputs prove the allocation order matches.
- `round((value + offset) * scale)` in profile synthesis is half-to-even → `pyRound`.
- Python's `timer or elapsed` treats 0.0 as falsy → JS `||`, not `??`.
- `validate` is NOT hoisted to the package root — Python's `__all__` doesn't; it lives
  at `chiptime/validate`. (The twin-surface rule, applied before the check fired.)
- `repair`/`NotRepairableError`/`RepairResult` ARE root exports, as in `__all__`.
