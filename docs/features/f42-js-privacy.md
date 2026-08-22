# Feature: F42 — `reveal` + `scrub` for TypeScript → npm `0.7.0`

> Status: DONE
>
> Lifecycle note: port of the already-critiqued F28 contract; no separate `/critique`
> pass. Gate: 8 invocation shapes (2 reveal, 6 scrub) across all 72 corpus cases,
> scrubbed-file **byte** comparison on the writing shapes.

## Purpose
`privacy.ts` — one category table read by both verbs, so the report can never
disagree with what the scrubber removes. `reveal` (read-only disclosure report,
coordinates rounded to ~1.1 km) and `scrub` (drop/null + optional GPS concealment
around route anchors, strict-mode self-check). CLI gains `reveal --json` and
`scrub --gps-radius/--drop-all-gps/--keep-*`. Surface = PyPI `0.7.0`.

## Gate
`check_cli_parity.py` grew from 2,163 to **2,667 invocations** — including the
everything-kept error path (`SCRUB_NOTHING_SELECTED`, exit 3) and both GPS modes.

## Notes
- privacy's haversine is its own function (radians per-coordinate, `min(1.0, h)`
  clamp, `2 * 6371000`), NOT the plausibility one (different op order) — ported
  op-for-op so the concealment radius decision is bit-identical.
- `round(x, 2)` for coarse coords → `pyRoundN`; report floats → `pyFloatStr`
  ("52.0"), with a hand-emitted sorted-key JSON in `revealJson`.
- `_null_fields` mirrors `FieldValue(None, None, units)`: the developer origin is
  dropped too, so a nulled dev field re-encodes exactly as Python's does.
- reveal/scrub map FitError → exit 4 only for `NOT_FIT_FORMAT`/`FIT_TOO_SMALL`
  (code-based, unlike the class-based mapping in other verbs) — ported as-is.
- Record concealment counts `bool(hit)` (0/1); summary concealment counts `hit`.
  Faithful asymmetry.
- Root exports gain `reveal`/`scrub`/`ScrubError`/`PrivacyReport` (+types),
  matching Python `__all__`; module at `chiptime/privacy`.
