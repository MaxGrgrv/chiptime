# chiptime (TypeScript)

**Recovery-grade FIT file processing.** Parse anything, lose nothing silently, explain everything.

The TypeScript twin of [`chiptime` on PyPI](https://pypi.org/project/chiptime/), built against the
same conformance corpus. Both implementations must produce byte-identical canonical JSON for every
case in `corpus/` — that shared corpus, not shared code, is the contract between them
([ADR-0001](../docs/architecture/adrs/0001-corpus-format.md),
[ADR-0009](../docs/architecture/adrs/0009-cross-language-parity.md)).

> **Status: pre-release scaffolding (F31).** Not published. The parsing surface arrives at F34/F35 —
> see [the M3 plan](../docs/m3-typescript-plan.md). What exists today is the determinism contract:
> the canonical serializer and the number kernel, both differentially tested against CPython.

## Parity

npm `0.N.0` mirrors the feature surface of PyPI `0.N.0`. Patch numbers are independent; from
`0.7.0` onward the two version lines move in lockstep.

| npm | mirrors | surface |
|---|---|---|
| `0.1.0` | PyPI `0.1.0` | decode, recovery, semantics, canonical JSON, `parse`/`inspect`/`codes` |
| `0.2.0` | PyPI `0.2.0` | encoder, `repair`, `validate` |
| `0.4.0` | PyPI `0.4.0` | `metrics`, `analyze` |
| `0.5.0`–`0.7.0` | same | `edit`, `trim`, `reveal`/`scrub` |
| `0.8.0`+ | same | `doctor`, and whatever else Python ships while this port runs |

There is no npm `0.3.0`: PyPI `0.3.0` was internal work (profile generation, performance, soak
fixes) that this port inherits from the code it mirrors.

The top of that table moves — Python keeps shipping while the port runs — so the two version lines
merge when npm catches up to the then-current Python version, not at a fixed number.

## Design constraints

- **Zero runtime dependencies.** Adding one requires an ADR, exactly as on the Python side.
- **Synchronous, everywhere.** Node, browsers, Deno and Bun run the same code path; container
  unwrapping uses an internal inflate rather than `node:zlib` or the async `DecompressionStream`.
- **No environment assumptions in `src/`.** No DOM lib, no `node:` import at module load.

## Development

```
npm install
npm run typecheck && npm run lint && npm test && npm run guards
```

The differential vectors under `test/vectors/` are generated from CPython by
`scripts/gen_parity_vectors.py` at the repo root and regenerated in CI — a Python-side behavior
change cannot silently invalidate them.

## License

MIT. Not affiliated with Garmin. FIT and Garmin are trademarks of Garmin Ltd.
