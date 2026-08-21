# Implementation: F28 — `reveal` + `scrub`

> Spec: [features/f28-privacy-scrub.md](../features/f28-privacy-scrub.md) · 2026-08-21 · Ships in 0.7.0

## What was built

`python/src/chiptime/privacy.py` — two verbs over one category table:

- **`reveal(src) -> PrivacyReport`** — read-only. Reports every disclosing
  message and field with counts, names the categories that are genuinely
  clean, and gives route endpoints **rounded to ~1.1 km**.
- **`scrub(src, …) -> ScrubResult`** — writes a cleaned file. Metadata
  categories (identity, serials, body metrics) default on because removing
  them costs no measurements; location concealment is opt-in because it does.

Plus CLI verbs `chiptime reveal` and `chiptime scrub`.

```text
$ chiptime reveal ride.fit
this file discloses:
  [serials] device_info.ant_device_number present in 22 message(s)
  [serials] device_info.serial_number present in 31 message(s)
  [serials] file_id.serial_number present in 1 message(s)
  [location] 9189 GPS points; the route starts and ends at real places
  route start ≈ 52.43, 13.75 · end ≈ 52.43, 13.74   (rounded to ~1 km so this report is safe to share)
  clean: identity, body_metrics
```

## The design decision that mattered most: `field_scope`

Testing on real files caught a false positive that would have destroyed real
data. `session.max_heart_rate` is *the highest heart rate reached during that
workout* — training data. `zones_target.max_heart_rate` is *the athlete's
configured physiological maximum* — personal. **Same field name, opposite
meaning.**

A naive name-based scrub removes both. So categories carry a `field_scope`:
fields count as personal only inside the messages named there, and an empty
scope means "personal wherever it appears" (a serial number always is).
Asserted by a test that scrubs a real file and checks the session's max HR
(155) survives untouched.

## Critique-mandated change, as built
**Radius is distance-based over every record**, not leading/trailing ones.
An index-based implementation would leak exactly what it claims to hide — a
loop that passes the house mid-route, or an out-and-back that touches home at
the turnaround. Concealment is `min(distance to first fix, distance to last
fix) <= radius`, which also yields Strava-style privacy-zone behaviour for
free. Tested: every surviving point is provably farther than the radius from
both original endpoints.

## Verified properties
| Property | How |
|---|---|
| Concealed positions decode as **absent**, never `0` | Round-trip test — Null Island is a real place (contract #4) |
| Totals survive a location scrub | distance/elapsed compared before and after on a real file: 29,613.68 m → 29,613.68 m |
| The output really is cleaner | `reveal` is run **on the scrubbed output** and must report no serials |
| Whole-route concealment is flagged | `SCRUB_ALL_POSITIONS_CONCEALED` warning when the radius swallows every point |
| Determinism | identical scrub twice → byte-identical |

## Honest limits (documented, not papered over)
Scrubbing removes *disclosed* data; it does not make a file untraceable.
Distance, speed, and duration remain on concealed records, and a determined
analyst could infer a route shape from them. The docs say so plainly rather
than implying anonymity.

Also found while auditing real files: `user_profile` and `zones_target` are
**absent from all three real activity files** — identity and physiology
travel mostly in settings files. The feature is still right, but the docs do
not imply every activity leaks your weight; `reveal` reports what is actually
present and names the clean categories.

## Verification
14 tests in `python/tests/test_privacy.py`: report coarseness, clean-category
honesty, serial removal verified *through* `reveal` on the output, the
field-scope regression, endpoint-vs-middle concealment with a distance proof,
absent-not-zero round-trip, totals invariance, whole-route warning,
determinism, platform validation, refusals, and the CLI. Full gate green:
ruff, format, mypy --strict, corpus (72 cases), 118 tests.

## Deviations from spec
- None material. Coordinate precision stayed fixed at 2 decimals (the
  configurable variant was cut at critique and sits in BACKLOG).
