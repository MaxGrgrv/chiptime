# Feature: F14 — Platform Validation Profiles

> Status: DONE

## Purpose
"Valid" is platform-relative (#99): Strava and Garmin Connect accept different files. Encode the folk knowledge as explicit, named checks (`strict-spec` / `garmin-connect` / `strava`) so repair output can be validated against its destination (#102) — marked heuristic, versioned in the open.

## Taxonomy Coverage
| Taxonomy item # | Summary | Coverage |
|---|---|---|
| 99 | Platform acceptance differs | validate() profiles + tests |
| 102 | Minimum-viable-file per platform | garmin-connect/strava check sets |
| 100/101 | Dedup identity, size limits | BACKLOG (need platform accounts / real upload probes to verify) |

No corpus cases: these validate *output acceptance*, not parse behavior; corpus inputs must also stay independent of chiptime (ADR-0001 §3), and repair output as a fixture would violate that. Unit tests + the strict-parse oracle carry this feature.

## Requirements
1. `chiptime/validate.py`: `validate(src, platform) -> list[Finding(level, code, detail)]`.
2. `strict-spec`: strict-mode parse must raise nothing (wire-level truth).
3. `garmin-connect` (folk knowledge, heuristic): complete file_id (type=activity, time_created, manufacturer), session + activity + ≥1 lap present, timer events present, records monotonic, session bounds cover records, local_timestamp plausible when present (the documented Zwift rejection).
4. `strava`: file_id.type=activity, ≥1 timestamped record; session absence is a warning (Strava tolerates more).
5. CLI `chiptime validate FILE --platform P`: exit 0 clean / 2 warnings / 3 errors.
6. Repair output for the Zwift-crash class must pass `garmin-connect`.

## Critique & Assessment
- **Alternatives considered:** claiming authoritative platform rules (rejected — unverifiable without upload probes; checks are explicitly heuristic and named VAL_*); merging into repair (rejected — validation is a read-only lens usable on any file).
- **Contract check:** findings carry stable codes + human sentences; nothing mutates.
- **Final decision:** APPROVE

## Dependencies
- **Depends on:** F13 · **Depended on by:** F16

## Related
- Implementation: [../implementation/f14-validation-profiles.md](../implementation/f14-validation-profiles.md)
