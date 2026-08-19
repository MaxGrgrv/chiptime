# ADR-0002: Canonical JSON via RFC 8785 (JCS), with a 64-bit string policy

> Status: ACCEPTED · 2026-08-17 · Feature: F2

## Context
Contract #2: same input bytes → byte-identical canonical JSON across runs, OSes, and languages (Python now, JS at M3). Naïve `json.dumps` differs from JS in float formatting, key order, and unicode escaping.

## Decision
1. **Serialization follows RFC 8785 (JSON Canonicalization Scheme)**: UTF-8, no whitespace, object keys sorted by UTF-16 code units, minimal string escaping, numbers formatted by ECMAScript `Number::toString` rules. Implemented internally (`chiptime/canonical.py`, ~150 lines, zero-dep) — JS gets JCS nearly for free at M3.
2. **Number policy** (stricter than JCS, enforced by the serializer):
   - `NaN`/`Infinity` are unrepresentable → decode maps them to `null` with a diagnostic long before serialization (taxonomy #35); the serializer raises if one leaks through (bug guard).
   - Integers beyond ±(2^53 − 1) are unrepresentable as JSON numbers without precision loss → the serializer **refuses** them; fields that can carry 64-bit raw values (uint64/sint64 raws) are serialized as decimal **strings** by the shaping layer, documented per field in the schema reference.
   - `-0.0` serializes as `0`.
3. **Determinism boundary**: `to_canonical_json()` excludes volatile facts — the local file *path* never appears (privacy + determinism); `source` carries only sha256/size/unwrapping. Wall-clock, locale, and env never influence output.
4. **Schema versioning**: top-level `"chiptime_schema": 1`. Any change to shaping (new fields, renames, number-policy changes) bumps it and regenerates corpus snapshots in the same PR.

## Alternatives considered
- `json.dumps(sort_keys=True)` + repr floats: Python-only determinism; breaks at M3 (JS float/exponent formatting differs at 1e16–1e21 and integral floats).
- Tagged strings for *all* numbers (toml-test style): maximally safe but makes the JSON hostile to direct human/agent consumption; our output is a product surface, not only a test artifact. String-encoding only the genuinely unsafe (64-bit raws) keeps both.

## Consequences
- A ~150-line well-tested serializer is on the critical path — covered by unit vectors + Hypothesis round-trip property (`float(serialized) == value`).
- The dict shape produced by the output layer must use only `None/bool/int/float/str/list/dict` — enforced by type checks in the serializer.
