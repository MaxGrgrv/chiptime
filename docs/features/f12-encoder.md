# Feature: F12 — FIT Encoder

> Status: DONE

## Purpose
Write valid FIT files (ADR-0006): the foundation of `chiptime repair` (F13) — the capability every OSS library lacks (research gap #2).

## Taxonomy Coverage
Infrastructure for #95→file, #96, #102 (F13/F14 land the cases). Round-trip property protects every decode behavior transitively.

## Requirements
1. `chiptime/encode.py`: `encode_messages(list[EncodableMessage]) -> bytes` per ADR-0006 (canonical wire form, slot manager, both CRCs).
2. Producers: `encodable_from_message` (lossless re-emit incl. unknown + compressed-timestamp materialization) and `encodable_from_profile` (reverse-scaled synthesis).
3. `Message.wire` retained from decode.
4. Round-trip + strict-clean contracts test-enforced on rich seeds (ride, dev-fields, multisport).

## Acceptance Criteria
- [x] parse→encode→parse semantic identity (offsets/source stripped)
- [x] Re-encoded files pass strict mode (0 defects)
- [x] Unknown messages/fields survive the round trip
- [x] Encoder deterministic (same messages → same bytes)

## Public API Impact
`chiptime.encode` module (documented as advanced/repair surface; not in top-level `__all__` yet — F13 exposes the user-facing verb).

## Critique & Assessment
- **Alternatives considered:** bit-preserving PRESERVE mode (rejected for repair — ADR-0006 §1); compressed-timestamp emission (rejected: size win is marginal, correctness risk real).
- **Risks identified:** reverse scaling rounding — locked by round-trip tests through real scale/offset fields (altitude's /5−500 among them); slot eviction untested at >16 shapes → test with 20 synthetic shapes.
- **Contract check:** encoder refuses nothing silently — unencodable values raise typed errors (it's a programming surface, not a hostile-input surface).
- **Final decision:** APPROVE

## Dependencies
- **Depends on:** F3 (profile/base types), F6 (dev metadata in stream) · **Depended on by:** F13, F14, F16

## Related
- ADR: [0006](../architecture/adrs/0006-encoder-policy.md)
- Implementation: [../implementation/f12-encoder.md](../implementation/f12-encoder.md)
