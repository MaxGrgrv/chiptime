# Feature: F3 — Decode Core

> Status: DONE

## Purpose
The streaming, crash-proof wire decoder: headers → frames → typed messages, with defects-as-values (ADR-0003) and the hand-authored core profile (ADR-0004). Everything else builds on this.

## Context Check
- [x] All five context docs reviewed; no duplication.

## Taxonomy Coverage

| Taxonomy item # | Summary | Corpus case(s) |
|---|---|---|
| 1 | Zero-byte file | structural/empty-file |
| 4 | Invalid file CRC → warn + continue | structural/file-crc-bad |
| 5 | Header CRC zero is legal; nonzero must match | structural/header-crc-zero, structural/header-crc-bad |
| 6 | Invalid header size | structural/header-size-invalid |
| 7 | data_size ≠ actual | structural/data-size-lies-short |
| 20 | Local message type redefinition | protocol/local-redefinition |
| 21 | Compressed timestamp headers + rollover | protocol/compressed-timestamps |
| 25 | Invalid base type / size mismatch → per-field salvage | protocol/invalid-base-type |
| 26 | Sentinel invalids → null | protocol/sentinel-values (also embedded in every seed) |
| 27 | Scale/offset application | clean/ride-smooth (altitude/speed/distance) |
| 32 | Big-endian definitions | protocol/big-endian |
| 33 | String edge cases (no NUL, bad UTF-8) | protocol/string-edges |
| 34 | Arrays with sentinel-padded tails | protocol/array-fields (hrv) |
| 35 | 64-bit ints; NaN/Inf floats → null + diagnostic | protocol/float-nan-inf, protocol/uint64-fields |
| 2 (partial) | Prefix salvage on truncation (resync lands in F5) | structural/truncated-mid-record (F5 finalizes) |

## Requirements
1. `read_frames(data)` never raises on content; emits FileHeader/Definition/Data/Crc/SkippedBytes/Defect with byte offsets.
2. Header handling: 12/14 byte; nonstandard sizes attempted via `.FIT` magic scan; header CRC `0x0000` = legal skip; data_size lies → trust actual bytes + defect.
3. Decoder: all 17 base types, per-definition endianness, arrays (element-wise sentinels; all-invalid → null), strings (NUL-split, UTF-8 `replace` + diagnostic), scale/offset, `date_time`/`local_date_time` → ISO strings (raw seconds retained), z-types, 64-bit (out-of-JSON-range raws as strings), NaN/Inf → null + diagnostic.
4. Compressed timestamps: 5-bit rollover from last anchor; missing anchor → recovered from `file_id.time_created` with warning (taxonomy #21 prescription).
5. Unknown globals/fields/enums preserved (`unknown_N`, `field_N`, raw ints) — contract #6.
6. `parse()` v0: bytes/path/stream → `ParseResult` (parts, messages, errors/warnings/provenance, recovery on prefix salvage, canonical JSON). Strict raises per ADR-0003.
7. Profile cross-check script green against fitdecode (ADR-0004 §2).

## Acceptance Criteria
- [x] All corpus cases above committed with snapshots; runner green in all three modes
- [x] Round-trip unit tests against `build_fit` fixtures (independent writer)
- [x] Profile checker: 0 mismatches on covered messages
- [x] Determinism double-parse holds on every case (runner-enforced)

## Public API Impact
`chiptime.parse`, `chiptime.Mode`, `chiptime.errors` (FitError + subclasses, codes), `ParseResult` (per PRD §7 minus semantic model — F7), canonical schema v1 initial shape.

## Architectural Placement
decode + profile layers; result/api scaffolding in output/api.

## Proposed Approach
Per ADR-0003/0004; see PRD §6.

## Critique & Assessment
- **Alternatives considered:** exception-based decode with recovery wrappers (rejected — ADR-0003 context); shipping the full generated profile now (rejected — requires maintainer SDK download + license acceptance; unknown-preservation makes breadth non-blocking, ADR-0004).
- **Risks identified:** hand-authored field numbers wrong from memory → mitigated by the fitdecode cross-check script (hard gate); ISO-formatting timestamps at decode layer could surprise (raw retained; semantic layer owns datetime math).
- **Simplification opportunities:** defer big-endian? Rejected — cheap (struct prefix) and Tier-2 #32 is real. Defer hrv arrays? Kept — array machinery is core, hrv is its natural test.
- **Contract check:** sentinels→null before anything (#26) ✓; no silent loss — every skip/salvage emits Defect→provenance ✓; determinism — no wall clock/randomness in decode ✓; errors carry code+offset+suggestion ✓; unknown preserved ✓.
- **Final decision:** APPROVE

## Dependencies
- **Depends on:** F1, F2
- **Depended on by:** F4–F16 (everything)

## Related
- ADR: [0003](../architecture/adrs/0003-defects-as-values-and-modes.md), [0004](../architecture/adrs/0004-profile-strategy.md)
- Implementation: [../implementation/f03-decode-core.md](../implementation/f03-decode-core.md)
