# Feature: F43 — `doctor` for TypeScript → npm `0.8.0` = version parity

> Status: DONE
>
> Lifecycle note: port of the already-critiqued F29 contract; no separate `/critique`
> pass. Gate: 4 `doctor` invocation shapes across all 72 corpus cases.
>
> **This release closes the staged-release plan: npm `0.8.0` = PyPI `0.8.0`,
> full version and surface parity. The lines are now in lockstep (ADR-0009 §9).**

## Purpose
`doctor.ts` — the join between `validate` and the fixing verbs: blocking vs
advisory findings, an ordered remedy table (repairable codes → the exact command),
honest `unresolved` for what has no automatic fix, and a one-line parse summary.
CLI gains `doctor --platform --json`. Surface = PyPI `0.8.0`.

## Gate
`check_cli_parity.py` grew from 2,667 to **2,955 invocations** — text and JSON
shapes against garmin-connect, strava, and strict-spec.

## Notes
- Python's `json.dumps` defaults to `ensure_ascii=True`: the summary's `·`
  separator must emit as `·`. `doctorJson` escapes non-ASCII after
  `JSON.stringify`.
- Python `doctor(src)` embeds the file *path* in prescribed commands when src is
  a str; the byte-only JS twin takes `srcName` (default `"FILE"`, same as
  Python's byte-source behavior). The CLI passes the path — identical output.
- Exit codes: `0` uploads, `2` blocked with remedies, `3` blocked without.
- Root exports gain `doctor`/`Diagnosis` (+`Remedy`/`DoctorOptions` types). The
  runtime root surface now equals Python `__all__` exactly under the camelCase
  mapping (`__version__` stays package.json metadata, per F31's decision).
