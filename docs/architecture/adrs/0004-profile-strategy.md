# ADR-0004: Profile strategy — hand-authored core, generator for breadth, never Garmin files

> Status: ACCEPTED · 2026-08-17 · Feature: F3

## Context
Message/field definitions ("Global FIT Profile") ship in Garmin's SDK under the FIT Protocol License — non-redistributable, anti-copyleft, terminable at will (docs/research/licensing-conformance-naming.md). Hard rules already in CLAUDE.md: no SDK dependency, no SDK files in repo. Downloading the SDK also requires accepting license terms — a maintainer action, not an automated one.

## Decision
1. **M1/M2 ship a hand-authored core profile** (`chiptime/profile/core.py`): the ~15 message types the semantic layer actually interprets (file_id, record, session, lap, event, activity, device_info, sport, length, hrv, field_description, developer_data_id, file_creator, user_profile, course/workout minimums) with field numbers, base types, scale/offset, units, and the enums we map. These are functional interface facts required for interoperability — the GoldenCheetah approach, and the material the license's §1 permits using in one's own software.
2. **Accuracy is verified, not trusted**: `scripts/check_profile_against_fitdecode.py` (dev-only, `baselines` group) diffs our tables against fitdecode's MIT-licensed generated profile and fails on mismatch. Run at authoring time and in `/verify` when profile files change. fitdecode is never imported by chiptime itself.
3. **Breadth comes later via the generator**: `scripts/generate_profile.py` (written when needed) converts a *maintainer-downloaded* SDK profile into `profile/generated.py` under our license with a provenance header (SDK version, date) — the 14-years-unchallenged fitparse/fitdecode pattern. Never run in CI; its output is reviewed and committed by a human.
4. **Profile absence is never fatal** (contract #6): any message/field not in our tables decodes as `unknown_*` with raw values preserved. A stale or narrow profile degrades to less *naming*, never to failure.

## Consequences
- M1 decodes every FIT file structurally; semantic naming covers the core set — exactly what the taxonomy needs.
- No Garmin-licensed byte ever enters the repo or the dependency tree.
- The JS port copies the same table data (our license) rather than re-deriving it.
