# Feature: F37 — The CLI for TypeScript, and npm `0.1.0`

> Status: DONE
>
> **Lifecycle note, stated plainly:** this feature did not get a separate `/critique` pass. The
> surface is a port of an already-critiqued contract (F11's exit codes, published in
> `docs/for-agents.md`), and its gate is exhaustive rather than sampled — 507 invocations compared
> byte for byte on stdout *and* exit code. Where earlier features needed a critique to decide what
> the gate should measure, here there was no such question. The compression was deliberate; it is
> recorded rather than glossed.

## Purpose

`chiptime parse | inspect | codes` in TypeScript, with the agent exit-code contract, and the first
npm release.

## Taxonomy Coverage

**None new** — the CLI surfaces behavior the layers below already implement. Its contract is
contract #5 (machine-parseable codes) and the exit-code table in `docs/for-agents.md`.

## Requirements

1. `parse`, `inspect`, `codes` mirroring `cli.py`'s M1 surface. The remaining verbs arrive with the
   features that implement them, exactly as they did in Python.
2. Exit codes: `0` clean · `2` recovered with loss · `3` unusable · `4` not FIT · `64` usage.
3. `--mode`, `--json`, `-o/--output`, `--strip-pii`, `--include-raw`, `--no-unknown`, `--limit`.
4. **`node:fs` imported at the top of `cli.ts` and nowhere else.** A command line implies a
   filesystem; the *library* must not. `index.ts` does not reach this module, so importing
   `chiptime` still pulls in no Node builtin — and the pack smoke asserts that distinction rather
   than banning the string everywhere.
5. `bin/chiptime.mjs` as the npm bin entry.
6. `main(argv, out, err)` takes injected writers so the parity harness can capture output without
   spawning 507 processes.

## Acceptance Criteria
- [x] **507 invocations** across all 72 corpus cases × 7 shapes, plus global cases: stdout bytes and
      exit codes identical
- [x] Usage errors exit 64 with the same message
- [x] `parse --json` emits canonical bytes on stdout
- [x] The pack smoke confirms the library imports no `node:` builtin; the CLI may and does
- [x] All prior gates still green

## Public API Impact

`chiptime` gains a `bin`. `main` is exported at `chiptime/cli`. No Python change.

## Architectural Placement

**`cli` layer** — the top. Imports `api`, `errors`, `numeric`, `result`, `model`; nothing imports it.

## Critique & Assessment

_Considered inline; no separate pass (see the status note)._

- **Alternatives considered:** spawning a process per invocation in the gate (rejected: 507 spawns
  to test output, not shell plumbing); a dependency for argument parsing (rejected: ADR-0009 §7,
  and the surface is seven flags).
- **Risks identified:** the summary renderer interpolates floats into prose, which is where every
  formatting divergence in this port has lived. Handled by `pyFixed`, `pyG` and `pyValue`, all
  vector-tested; the 507-invocation gate is what proves it.
- **Contract check:** exit codes are the agent contract and are compared on every invocation.
  Nothing here can lose data — the CLI only renders what `parse()` produced.
- **Final decision:** APPROVE.

## Dependencies
- **Depends on:** F31–F36; F11 in Python as the reference
- **Depended on by:** F38+ (each new verb extends this CLI)

## Related
- Plan: [../m3-typescript-plan.md](../m3-typescript-plan.md)
- Implementation: [../implementation/f37-js-cli.md](../implementation/f37-js-cli.md)
