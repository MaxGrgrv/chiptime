# Feature: F2 — Corpus Infrastructure + Canonical Serializer

> Status: DONE

## Purpose
Build the conformance machinery everything else is tested against: the corpus case format and tools (ADR-0001), and the RFC 8785 canonical JSON serializer (ADR-0002) that defines "byte-identical output".

## Context Check
- [x] All five context docs reviewed; no duplication.

## Taxonomy Coverage
Enables contract #2 (determinism) and #7 (corpus). Individual taxonomy cases land with the features that implement their behavior (F3+), because `expected.json` requires a parser.

| Taxonomy item # | Summary | Corpus case(s) planned |
|---|---|---|
| — (infrastructure) | Corpus format, generators, runner, canonicalizer | seeds + runner harness |

## Requirements
1. `chiptime.canonical.dumps(obj) -> bytes` implementing JCS with the ADR-0002 number policy.
2. `corpus/tools/build_fit.py` — self-contained deterministic FIT writer (own CRC/base-type tables; independent of chiptime by design) + named seed builders (`ride_smooth`, `run_basic`).
3. `corpus/tools/corrupt.py` — deterministic byte-level ops: truncate, flip bit, overwrite, insert, delete, zero/garble CRCs, lie about data_size, chain, gzip/zip wrap, non-FIT payloads.
4. `corpus/tools/gen_all.py` — regenerate every case's `input.fit` from its `case.json` build pipeline; verify/record sha256; write `MANIFEST.json`; `--expected` flag (used from F3 on) regenerates snapshots via chiptime.
5. Conformance runner `python/tests/conformance/test_corpus.py`: for each manifest case — sha256 guard, lenient parse == expected bytes, per-mode expectations honored.
6. `corpus/README.md` documenting the format for humans and agents.

## Acceptance Criteria
- [x] JCS vectors + Hypothesis float round-trip pass
- [x] Seeds build byte-identically twice (determinism of tools themselves)
- [x] Runner discovers zero cases gracefully (corpus fills from F3)

## Public API Impact
`chiptime.canonical.dumps` (internal-ish but exported for tooling). No schema yet.

## Architectural Placement
`output` layer (canonical.py) + corpus tooling (outside the package).

## Proposed Approach
Per ADR-0001/0002.

## Critique & Assessment
- **Alternatives considered:** reusing chiptime's future encoder for fixtures (rejected — shared-bug blindness, ADR-0001 §3); `json.dumps` canonicalization (rejected — ADR-0002).
- **Risks identified:** ES6 number formatting subtly wrong → mitigated with vector tests + property round-trip; fixture-writer wire bugs → cross-checked against fitdecode in F3 (baselines group).
- **Simplification opportunities:** zip/tcx/gpx wrappers could wait for F4 — kept, they're ~20 lines and complete the ops vocabulary.
- **Contract check:** canonicalizer refuses NaN/Inf/oversized ints (silent-corruption guard); corpus sha256 guard prevents silent hand-edits.
- **Final decision:** APPROVE

## Dependencies
- **Depends on:** F1
- **Depended on by:** F3+ (all corpus-tested features), M3 JS parity

## Related
- ADR: [0001](../architecture/adrs/0001-corpus-format.md), [0002](../architecture/adrs/0002-canonical-json.md)
- Implementation: [../implementation/f02-corpus-and-canonical.md](../implementation/f02-corpus-and-canonical.md)
