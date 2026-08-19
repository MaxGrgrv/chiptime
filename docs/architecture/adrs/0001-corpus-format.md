# ADR-0001: Conformance corpus format and generation rules

> Status: ACCEPTED · 2026-08-17 · Feature: F2

## Context
The corpus is the cross-language conformance contract (PRD §9). It must be reviewable, deterministic, license-clean, and consumable by the future JS implementation unchanged. Research: toml-test (fault-named cases, external-runner growth path), JSON-Schema-Test-Suite (data-only repo + native loaders).

## Decision
1. **Triplet per case** at `corpus/cases/<category>/<slug>/`:
   - `input.fit` — the bytes under test (possibly deliberately corrupt, possibly not FIT at all)
   - `expected.json` — exact canonical output bytes (`ParseResult.to_canonical_json()`, lenient mode)
   - `case.json` — metadata: taxonomy item refs, tier, graded expectation (`ok | partial | reject`), per-mode expectations (`strict: "raise:<CODE>"` etc.), deterministic build pipeline, recorded `input_sha256`, source, notes
2. **Inputs are generated, never hand-edited.** Every `input.fit` is reproducible from `case.json`'s `build` pipeline (`seed` op + corruption ops with explicit offsets/bytes — no randomness anywhere). `corpus/tools/gen_all.py` regenerates and verifies sha256; the conformance runner re-verifies sha256 at test time so a hand-edited binary fails loudly.
3. **Fixture tooling is independent of the library under test.** `corpus/tools/build_fit.py` is a self-contained FIT writer with its own CRC and base-type tables. Deliberate duplication: if the parser and the fixtures shared code, a shared bug would cancel out and the corpus would prove nothing.
4. **License hygiene**: no Garmin SDK sample files, no downloaded third-party binaries. Sources allowed: `synthetic` (tools), `own-archive` (user's device files, PII-stripped, explicitly consented), `donated` (with consent note). M1 is fully synthetic; ★ own-archive items join when provided.
5. **Consumption**: native loaders (pytest now, vitest at M3) reading `corpus/MANIFEST.json` (generated). A stdin/stdout subprocess protocol can be added later for third-party implementations without changing the data.
6. **Small inputs by design** (tens of records, not thousands) so `expected.json` stays reviewable in a PR. Scale behavior is covered by property/fuzz tests, not snapshots.

## Consequences
- Changing canonical schema ⇒ regenerate all `expected.json` (one command), diff reviewed in the PR — schema changes stay visible and deliberate.
- The corpus can be extracted to its own repo later without code changes (data-only).
- Real-device quirks enter as recorded byte patterns in build pipelines (e.g. replayed defect bytes), keeping determinism.
