# Feature: F40 — `edit` for TypeScript → npm `0.5.0`

> Status: DONE
>
> Lifecycle note: port of the already-critiqued F26 contract; no separate `/critique`
> pass. Gate: 7 `edit` invocation shapes across all 72 corpus cases, with edited-file
> **byte** comparison on the shapes that write.

## Purpose
`edit.ts` — user-directed metadata surgery (sport/sub-sport, recording-device
identity, time shift, distance rescale) with provenance per edit and a strict-mode
re-parse self-check. CLI gains `edit` with `--sport/--sub-sport/--manufacturer/
--product/--time-shift/--total-distance`. Surface = PyPI `0.5.0`.

## Gate
`check_cli_parity.py` grew from 1,155 to **1,659 invocations** and now assigns each
writing invocation its own output file (`slug.i<idx>.SIDE.fit`), so `repair` and the
five writing `edit` shapes are byte-compared independently — previously all shapes
shared one path and later writes could mask earlier divergence.

## Notes
- Python's `{v!r}` in provenance details → local `pyRepr` (strings quoted, None).
- `round()` in distance rescale is half-even → `pyRound`; `{x:.Nf}` → `pyFixed`.
- `if time_shift_s:` — a zero shift is falsy and skips; the CLI's "at least one
  change" check treats a parsed `0` shift the same way. Both ported as truthiness.
- `derived.distance_m or declared...` → `||` (0.0 falls through), `current or 0.0`.
- `_fits` z-type quirk kept: `uint*z` invalid is 0, so `0 <= raw < 0` never holds.
- Root exports gain `edit`/`EditError` (+`EditResult`/`EditOptions` types), matching
  Python `__all__`; module also at `chiptime/edit`.
