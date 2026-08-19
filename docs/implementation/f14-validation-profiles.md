# Implementation: F14 — Platform Validation Profiles

> Feature Spec: [../features/f14-validation-profiles.md](../features/f14-validation-profiles.md)

## Summary
`chiptime/validate.py` + `chiptime validate --platform`: strict-spec (wire oracle), garmin-connect (file_id completeness, session/activity/lap presence, events, monotonicity, the Zwift local_timestamp rejection class), strava (looser: records required, session a warning). The M2 loop closes: **`no_session` fails GC with 3 errors → `repair()` → passes clean** (test-locked).

## Files Changed
| File | Change Type | Description |
|------|------------|-------------|
| python/src/chiptime/validate.py | Added | Profiles + Finding model |
| python/src/chiptime/cli.py | Modified | validate subcommand (0/2/3 exit) |
| python/tests/test_validate.py | Added | 6 tests incl. repair→validate integration |

## Key Implementation Decisions
1. Checks are named `VAL_*` and openly heuristic — platform rules are folk knowledge; corrections should be one-line PRs.
2. strict-spec delegates entirely to strict parsing — one oracle, no duplicate spec logic.
3. GC monotonicity check keys off `RECORDS_REORDERED` provenance (the parser already knows), noting that repair re-emits sorted.

## Post-Implementation Checklist
- [x] Spec DONE · INDEX/OVERVIEW updated · 184 tests green · ruff/mypy clean
- [x] Read-only lens; stable finding codes
