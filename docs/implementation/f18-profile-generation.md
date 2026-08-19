# Implementation: F18 — Full Profile Generation

> Feature Spec: [../features/f18-profile-generation.md](../features/f18-profile-generation.md)

## Summary
`scripts/generate_profile.py` (stdlib-only xlsx reader: zip + ElementTree, zero new deps even for dev) parsed the maintainer's local SDK 21.158.00 into `profile/generated.py`: **119 messages / 1,382 fields / 176 enums (3,640 values)**, deterministic output, provenance header, global semicircles→degrees rule. Field-level merge in `profile/__init__` (generated breadth, verified core wins per-field). Extended fitdecode gate: **every one of the 1,382 fields verified identical** against fitdecode's independently-generated profile (0 mismatches, 0 skew).

## Measured payoff (soak re-run, 66 real files)
- Files with >30% unknown messages: **9 → 0** (workouts were 66–71%, monitoring 95%)
- Contract still perfect: 0 violations
- Corpus: monitoring-file case re-snapshot with named semantics (deliberate)

## Files Changed
| File | Change | Description |
|---|---|---|
| scripts/generate_profile.py | Added | SDK→tables generator (ADR-0004 §3, now real) |
| python/src/chiptime/profile/generated.py | Added (generated) | The breadth tables |
| python/src/chiptime/profile/__init__.py | Modified | Field-level merge policy |
| scripts/check_profile_against_fitdecode.py | Modified | Strict pass = core; intersection pass = full merged tables |
| python/pyproject.toml | Modified | E501 per-file-ignore for the generated file |

## Key Implementation Decisions
1. Subfield rows (no Field Def #) deliberately skipped — dynamic resolution stays curated (F15's event.data); component multi-scales keep raw values. Both noted for future depth.
2. `semicircles` units globally become degrees at scale — core's documented divergence applied uniformly so course_point etc. match record positions.
3. Generator embeds SDK version but no wall-clock date — regeneration is byte-reproducible.

## Post-Implementation Checklist
- [x] Spec DONE · INDEX updated · 203 tests green (64 conformance) · ruff/mypy clean, exit codes checked
- [x] No Garmin file in repo (zip read from ~/Downloads only); non-affiliation note in generated header
