# Feature: F17 — Soak-Sprint Fixes (M2.5)

> Status: DONE

## Purpose
First real-world contact (66 files, 0 contract violations) surfaced three concrete defects. Fix them: honest error for valid-but-empty shells (#16 — found in the wild as a 16-byte fitfiletools output), sport-aware distance-frozen gating (20 warnings, mostly swim false-positives), and repair dropping implausible local_timestamp (4 real files repaired to GC-invalid output).

## Taxonomy Coverage
| # | Summary | Corpus case |
|---|---|---|
| 16 | Structurally valid, genuinely empty → explicit honest error | structural/empty-shell |
| 37 (repair leg) | Repair must not re-emit the Zwift local_timestamp bug | temporal/zwift case + repair test |
| 56/73 (flag hygiene) | Swim distance legitimately freezes | sensors gating test |

## Requirements
1. `FIT_NO_CONTENT` error when a part parses cleanly but contains zero messages: `ok=false` must never come with empty `errors[]` (contract #5). Strict does NOT raise (an empty FIT is spec-legal) — it returns the same honest reject.
2. `DISTANCE_FROZEN` skipped for `swimming` sessions (distance steps by design between lengths/fixes); decreases/reset checks stay universal.
3. Repair: when the activity message carries an implausible `local_timestamp` (device-relative or |offset| > 26 h), the re-emitted message carries the invalid sentinel instead (field honestly absent) + `REPAIR_LOCAL_TIMESTAMP_DROPPED` provenance. Latent bug fixed alongside: `_local_offset` must ignore sentinel raws (0xFFFFFFFF previously flagged as "implausible offset").
4. Soak harness (`scripts/soak_real_files.py`) committed as standing infrastructure.

## Acceptance Criteria
- [x] 16-byte shell: `ok=false`, `errors=[FIT_NO_CONTENT]`, same in all three modes, no fabrication
- [x] Swim files raise no DISTANCE_FROZEN; cycling keeps the check
- [x] zwift-class file: repair → validate garmin-connect = clean (was VAL_GC_LOCAL_TIMESTAMP)
- [x] Soak re-run: repaired-but-GC-invalid drops 4 → 0

## Critique & Assessment
- **Alternatives considered:** synthesizing local_timestamp = UTC (offset 0) in repair — rejected: a wrong-but-plausible value is worse than an honest absence (contract #8); GC accepts files without local_timestamp.
- **Contract check:** new error carries code+detail+suggestion; repair change adds provenance; gating removes a false positive, not a detection.
- **Final decision:** APPROVE

## Dependencies
- **Depends on:** F9/F13/F15 · **Depended on by:** F19 (corpus promotion needs clean flags)

## Related
- Implementation: [../implementation/f17-soak-fixes.md](../implementation/f17-soak-fixes.md)
