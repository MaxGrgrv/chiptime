# Implementation: F37 — The CLI for TypeScript

> Feature Spec: [../features/f37-js-cli.md](../features/f37-js-cli.md)

## Summary

`chiptime parse | inspect | codes` in TypeScript. **507 invocations across all 72 corpus cases
produce identical stdout bytes and identical exit codes.**

With this, the npm package matches the surface PyPI `0.1.0` shipped, and `0.1.0` is releasable.

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `js/src/cli.ts` | Added | `parse`/`inspect`/`codes`, exit codes, summary renderer |
| `js/bin/chiptime.mjs` | Added | npm bin entry |
| `js/src/numeric.ts` | Modified | `pyG` (Python's `:g`) |
| `js/package.json` | Modified | `bin`, `files`, `chiptime/cli` export |
| `js/scripts/smoke.sh` | Modified | Excludes the CLI from the `node:` ban, with the reason |
| `scripts/check_cli_parity.py` | Added | The 507-invocation gate |
| `scripts/gen_codes_ts.py` | Modified | Emits in **source** order, not sorted |
| `.github/workflows/ci.yml`, `.githooks/pre-push` | Modified | CLI parity gate |

## Deviations from Spec

None.

## Lessons Learned

- **Sorting a generated table changed user-visible output.** `gen_codes_ts.py` sorted the code
  registries "for determinism". Python dicts preserve insertion order and `chiptime codes` prints
  them in it, so the sort made the CLI's output diverge — caught by the one global invocation in
  the gate. Source order is exactly as deterministic and is the actual contract. The general
  lesson: *determinism* and *the right order* are different requirements, and choosing an arbitrary
  deterministic order is still a choice about output.

- **`require` does not exist in ESM, and the failure looked like a usage error.** The first CLI
  draft loaded `node:fs` through `require()` to keep it lazy. In an ES module that throws, the
  throw was caught by the file-read handler, and **all 505 file-based invocations returned exit
  64** — a plausible-looking "usage error" for what was actually a module-system mistake. A gate
  that compares exit codes caught it instantly; one that only compared stdout on success would not
  have.

  The fix reframed the invariant correctly: the *library* must import no Node builtin, not every
  file in `dist`. The CLI legitimately does, and the smoke check now says so by name.

- **`pyG` was the fourth formatting helper this port has needed.** Python's `:g` has no JavaScript
  equivalent at all — `String(1234.5678)` is `"1234.5678"` where `f"{x:g}"` is `"1234.57"`. Along
  with `pyValue` (`None` renders as `"None"`, not `"null"`), that is six divergences now, every one
  of them in text rather than in numbers, and every one invisible to a side-by-side reading.

## Post-Implementation Checklist
- [x] Feature spec status updated to DONE
- [x] INDEX.md updated
- [x] DEPENDENCY_MAP.md updated
- [x] Architecture docs updated
- [x] All new behavior covered by the 507-invocation parity gate
- [x] Provenance — N/A: the CLI renders, it does not transform
- [x] Determinism verified (all prior gates still green)
