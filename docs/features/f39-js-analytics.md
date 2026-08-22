# Feature: F39 — Analytics (`metrics/`, `analyze`) for TypeScript → npm `0.4.0`

> Status: DONE
>
> Lifecycle note: port of the already-critiqued F16–F22 analytics contracts; no separate
> `/critique` pass. Gate: `analyze` in 5 invocation shapes across all 72 corpus cases.

## Purpose
The nine `metrics/` modules — `settings`, `sports`, `pacing`, `basics` (mean-max,
time-in-zones, SWOLF), `zones`, `load` (TRIMP, workout load, fitness/fatigue/form),
`intervals` (detection ladder), `insights` (report builder + JSON serializer) — plus
CLI `analyze` with `--ftp/--max-hr/--resting-hr/--sex/--hr-zones/--power-zones/--json`.
Surface = PyPI `0.4.0` (npm skips 0.3.0 per the staged-release plan; `chiptime codes`
shipped in F37).

## Gate
`check_cli_parity.py` grew from 795 to **1,155 invocations**: `analyze` plain,
`--json`, `--json` + settings, `--json` + zones + sex, `--power-zones` text — stdout
bytes and exit codes identical, with one measured exception below.

## ULP tolerance for analytics JSON (ADR-0009 §6 extension)
18 of the first run's divergences were last-ULP differences in `exp`/`pow` results
(`weighted_avg_power`'s `**0.25`, TRIMP's `e^x`) reaching *unrounded* `--json` fields.
CPython delegates those to platform libm — its own output is OS-dependent there — so
`--json` full-precision floats compare with rel 1e-12 tolerance (`_tolerant_equal`).
Canonical parse output remains byte-exact; only `analyze --json` gets the tolerance.

## Notes
- `pyMedian` / `pyPstdev` added to `numeric.ts` (statistics.median / pstdev twins).
- Report JSON: Python ints (`INT_FIELDS` = index/count/first_index/step_index/lengths)
  emit bare; every other integral float emits with `.0` — `dumpsReportJson`.
- `isoPlus00` handles fractional FIT timestamps: microseconds via `pyRound` (half-even)
  with carry at 1e6 — a swim's `end_time` exposed the naive path.
- Faithful quirk kept: the laps rung of interval detection has `start`/`end` = null
  always (Python's `isinstance(str, datetime)` is False — dead code, ported as-is).
- Python `statistics` builtin `sum()` → `pySum` (Neumaier); plain `+=` loops stay naive.
- `fitnessFatigueForm` does civil date math on strings — no `Date`, per the guard.
