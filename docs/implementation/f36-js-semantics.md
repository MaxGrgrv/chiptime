# Implementation: F36 — The semantic model for TypeScript

> Feature Spec: [../features/f36-js-semantics.md](../features/f36-js-semantics.md)
> Plan: [../m3-typescript-plan.md](../m3-typescript-plan.md) · Contract: [ADR-0009](../architecture/adrs/0009-cross-language-parity.md)

## Summary

**All 72 corpus cases are byte-identical to their committed `expected.json`.** The parity claim
ADR-0001 made in the abstract is now a measured fact across the whole conformance suite, in all
three modes, from an independent implementation.

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `js/src/model.ts` | Added | The canonical model; times as FIT seconds, never `Date` |
| `js/src/semantics/{timers,gaps,plausibility,reconcile,build}.ts` | Added | ~1,490 lines ported |
| `js/src/numeric.ts` | Modified | `pySum`, `pyFixed`, `pyFloatStr` |
| `js/src/result.ts` | Modified | The `activity` block's canonical shaping |
| `js/src/api.ts` | Modified | `parse()` builds the activity for activity parts |
| `js/test/numeric.test.ts` | Modified | 106 new differential vectors |
| `scripts/check_parse_parity.py` | Modified | **Tiers removed**; all 72 vs `expected.json` |
| `scripts/gen_parity_vectors.py` | Modified | Format/summation vectors; `allow_nan=False` |

## Corpus Cases Added

None — sixth feature running, and the last one where that matters. The 72 committed snapshots were
the specification; nothing about them changed.

## Key Implementation Decisions

1. **Times are FIT seconds throughout the model.** Python holds `datetime`; the TypeScript model
   holds integers and formats at the boundary. Forced by the `Date` ban (ADR-0009 §5) and correct
   anyway — every timestamp in the activity block goes through `strftime`, which the integer
   formatter reproduces exactly.

2. **`iso()` floors before formatting.** A model time can be fractional (`end = start + elapsed`
   where elapsed is a float); Python holds that as a `datetime` with microseconds and `strftime`
   drops them. Truncating at the formatting boundary keeps the civil-date arithmetic integral.

3. **The two-tier gate was deleted, not left inert** (Requirement 18). It existed only because the
   semantic model did not.

## Deviations from Spec

None. Amendment E1 (the haversine measurement in ADR-0009 §6) was applied at critique time; the
`gps/*` cases passed with the haversine as ported, exactly as the pre-port measurement predicted.

## Lessons Learned

- **`sum()` is not a loop of additions, and that cost 18 corpus cases.** Since CPython 3.12 the
  builtin's float fast path runs the improved Kahan–Babuška (Neumaier) algorithm with a running
  compensation term. `sum([8.333] * 120)` is exactly `999.96`; `total += v` gives
  `999.959999999999`. The difference reached canonical output through every derived average.

  This is the single most instructive find of the port. `sum()` is the most ordinary function in
  Python; the naive port is *what it looks like it does*; no amount of reading the two sources side
  by side would reveal it; and the only thing that caught it was a byte comparison against a
  committed snapshot. Every other numeric hazard so far was at least visible in the source
  (`Math.round`, `toFixed`, bitwise width). This one was invisible in both.

- **The port's numeric kernel grew three functions in this feature alone**, all for hazards with
  the same shape: `pySum` (compensated summation), `pyFixed` (`f"{x:.Nf}"` rounds half-to-even),
  `pyFloatStr` (`str(55.0)` is `"55.0"`). Negative zero broke two of them on first write — `round()`
  returns an int and has no `-0`, but *formatting* preserves the sign. Vectors caught all of it.

- **The pre-port measurement of the haversine changed how the feature felt to build.** It was the
  spec's headline risk; measuring it first (53/54 bit-identical, worst case one ULP) removed it
  from the working set entirely, and attention went to the ordinary hazards that turned out to
  matter. Cheap measurement of the scariest assumption is worth doing before, not during.

- **The vector generator wrote invalid JSON and nothing noticed.** `json.dumps` emits bare
  `Infinity` by default. Now `allow_nan=False`, so it fails at generation rather than at test load.
  Second time this feature's tooling has needed hardening — the first was `gzip.compress`'s MTIME.

## Post-Implementation Checklist
- [x] Feature spec status updated to DONE
- [x] INDEX.md updated
- [x] DEPENDENCY_MAP.md updated
- [x] Architecture docs updated
- [x] All new behavior covered by unit tests (740 total) and the 72-case snapshot gate
- [x] Every new drop/repair/reinterpretation emits provenance — `SESSION_REBUILT`,
      `RECORDS_REORDERED`, `TIMER_STOP_SYNTHESIZED`, `ENHANCED_PAIR_MERGED`, `NULL_ISLAND_DROPPED`,
      `GPS_SPIKES_DROPPED`, `VIRTUAL_GPS_EXEMPT`, all byte-gated
- [x] Determinism verified (all three modes; double-parse identical)
- [ ] Skills assessed and updated (`/post-impl-review`)
