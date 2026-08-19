# Implementation: F2 — Corpus Infrastructure + Canonical Serializer

> Feature Spec: [../features/f02-corpus-and-canonical.md](../features/f02-corpus-and-canonical.md)

## Summary
JCS canonicalizer (`chiptime/canonical.py`, 22 tests incl. Hypothesis round-trip), self-contained deterministic FIT fixture writer with two seeds (`ride_smooth` 3489 B, `run_basic` 1695 B), corruption op vocabulary, `gen_all.py` regenerate/verify pipeline with sha256 guards, MANIFEST generation, and the conformance pytest runner (sha guard → snapshot compare → per-mode grade assertions → double-parse determinism).

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| python/src/chiptime/canonical.py | Added | RFC 8785 serializer; ES6 number formatting; NaN/Inf/big-int refusal |
| python/tests/test_canonical.py | Added | Vectors + property tests + UTF-16 key-order proof |
| corpus/tools/build_fit.py | Added | Standalone FIT writer (own CRC/base-type tables), seeds registry |
| corpus/tools/corrupt.py | Added | truncate/flip/overwrite/insert/delete/append, CRC ops, data_size lie, chain, gzip/zip wrap, non-FIT payloads |
| corpus/tools/gen_all.py | Added | Pipeline executor, double-build determinism check, sha recording, MANIFEST, `--expected` |
| corpus/README.md | Added | Format documentation (agents + humans) |
| python/tests/conformance/test_corpus.py | Added | The conformance runner |

## Corpus Cases Added
None yet by design — `expected.json` requires `chiptime.parse` (F3). Runner currently collects 0 cases and skips.

## Key Implementation Decisions
1. **Seeds built in-memory, not committed** — the `seed` op materializes from `build_fit.SEEDS` at generation time; only per-case `input.fit` bytes are committed (sha-guarded). One less binary class to keep in sync.
2. ES6 number formatting implemented by re-presenting Python's shortest-round-trip `repr` digits under ECMAScript rules (k/n thresholds 21 and −6) rather than reimplementing digit generation — small, provably round-trips.
3. Records in `ride_smooth` deliberately embed taxonomy #64/#68 raw material: real 0 W coasting (i∈[30,35)) and a power-field dropout via a second record definition (i∈[50,56)).
4. Runner asserts *forensic never raises* and double-parses both lenient and forensic — determinism is checked on every corpus case forever, not in a separate suite.

## Deviations from Spec
- None.

## Lessons Learned
The JCS "sort by UTF-16 code units" subtlety (surrogates vs BMP) is real and testable — `\U0001F600` sorts *before* `U+FF5F`; a naive Python `sorted()` would get this wrong. The JS port must not "simplify" this.

## Post-Implementation Checklist
- [x] Feature spec status updated to DONE
- [x] INDEX.md updated
- [x] DEPENDENCY_MAP.md updated (no changes needed — zero runtime deps held)
- [x] Architecture docs updated (canonical.py noted under output layer)
- [x] All new behavior covered by unit tests
- [x] Provenance N/A (no parse paths yet)
- [x] Determinism: serializer property-tested; seeds double-build-checked
- [x] Skills assessed — no updates needed
