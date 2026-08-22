# Feature: F41 — `trim` for TypeScript → npm `0.6.0`

> Status: DONE
>
> Lifecycle note: port of the already-critiqued F27 contract; no separate `/critique`
> pass. Gate: 7 `trim` invocation shapes across all 72 corpus cases, trimmed-file
> **byte** comparison on the writing shapes.

## Purpose
`trim.ts` — crop to a time window, then rebuild session/activity totals from the
survivors via the ordinary semantic layer (`buildActivity`) so nothing stale is
carried forward. CLI gains `trim --after/--before`. Surface = PyPI `0.6.0`.

## Gate
`check_cli_parity.py` grew from 1,659 to **2,163 invocations** — relative bounds
(`+5s`, `=-5s`, `+2m/-30s`), a keep-everything absolute ISO bound, a bad bound
(exit 3), and a windowless call (exit 64).

## Notes
- `repair.ts`'s `summaryMessage` gained `firstLapIndex`/`numLaps` params and is
  exported for trim (Python: `from chiptime.repair import _summary_message`).
- argparse fidelity: `--before -10m` is refused ("option-looking token"), while
  `--before=-10m` and plain negative numbers are accepted — `NEGATIVE_NUMBER`
  matcher + `=`-split with an inline-value exemption, exactly argparse's rules.
- **Documented deviation** (ADR-0009 §6 spirit): a *naive* ISO bound is read as
  UTC. CPython interprets it in the machine's local timezone — same input,
  different output per host — so byte-matching it is a phantom target. Aware
  strings (`Z`, `±HH:MM`) agree exactly; `daysFromCivil` inverts the decoder's
  `civilFromUnix`, no `Date`.
- `rebuild_prov` from `buildActivity` is created and discarded — faithful quirk.
- Root exports gain `trim`/`TrimError` (+types), matching Python `__all__`.
