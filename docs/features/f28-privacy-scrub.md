# Feature: F28 — `scrub` + `reveal`: privacy for files you share

> Status: DONE

## Purpose

A FIT file discloses far more than a route. Alongside GPS traces that begin
and end at your front door, files routinely carry device serial numbers,
age, gender, height, weight, resting and max heart rate, VO2max and FTP —
and almost nobody knows, because nothing surfaces it. People share these
files with coaches, paste them into forum threads asking for help, and
attach them to bug reports.

Research (`docs/internal/research-fit-jobs-2026-08.md`, job #12) rates this
demand MED-and-growing and — uniquely among the twelve jobs — **under-served:
no mainstream one-click sanitiser exists**, and the "what does this file
reveal about me" question has no incumbent answer at all.

Two verbs, because they answer two different questions:

- **`reveal`** — *what does this file disclose?* Read-only, writes nothing.
- **`scrub`** — *remove it*, and write a file that still parses and uploads.

chiptime already has a narrow parse-time `strip_pii=True` (drops
`user_profile`, nulls `serial_number`) that only affects JSON output. F28
generalizes it into a real file→file operation with the categories users
actually care about.

## Context Check
- [x] docs/INDEX.md — no file→file privacy feature exists; `strip_pii` is output-only
- [x] docs/architecture/OVERVIEW.md — write layer, beside `edit`/`trim`/`repair`
- [x] docs/dependencies/DEPENDENCY_MAP.md — no cycles
- [x] docs/PRD.md — user-directed write (amended non-goal); ADR-0007 established the PII stance
- [x] docs/edge-case-taxonomy.md — touches #57 (virtual/absent GPS), sentinel handling for nulled positions
- [x] No duplication — extends `strip_pii` rather than competing with it

## Taxonomy Coverage

Write-side feature. It must not regress:

| Taxonomy item # | Summary | Corpus case(s) |
|---|---|---|
| 26 | Sentinel/invalid values decode to null and re-encode as invalid | existing `protocol/sentinel-values` (reused: nulled positions must round-trip as *invalid*, not 0) |
| 57 | Virtual/absent GPS must stay absent, never fabricated | existing `gps/virtual-gps-zwift` |

No new corpus inputs planned; assertions run against committed cases plus
the private real-file tier (which has genuine home coordinates).

## Requirements

1. **`reveal(src) -> PrivacyReport`** listing what the file discloses, by
   category: `location`, `identity`, `body_metrics`, `device_serials`.
   Each finding names the message and field, and says how many records carry
   it. **Coordinates are reported coarsely** (≈ city-level, 2 decimal
   places) by default: a disclosure report that itself prints your front
   door is a footgun, since the whole point is that people paste these
   places they shouldn't.
2. **`scrub(src, *, identity=True, serials=True, body_metrics=True,
   gps_radius_m=None, drop_all_gps=False, mode="lenient") -> ScrubResult`.**
3. **Metadata categories are on by default** (they remove no measurements):
   - `identity` — the `user_profile` message (name, gender, age, height, weight)
   - `serials` — `serial_number` in `file_id`, `device_info`, and ANT device ids
   - `body_metrics` — `zones_target` (FTP, max/threshold HR) and VO2max-carrying fields
4. **Location scrubbing is opt-in and explicit**, because it removes
   measurements: `gps_radius_m=R` nulls `position_lat`/`position_long` on
   every record within R metres of the **first or last** GPS fix — the
   endpoints that identify a home or workplace — and nulls
   `start_position_*`/`end_position_*` on session and lap summaries, which
   carry the same coordinates in plain sight.
5. **Nulled positions become FIT *invalid*, never zero** — the difference
   between "no reading" and "the equator" (contract #4). Everything else on
   those records (heart rate, power, distance) is preserved.
6. **Totals are untouched and remain correct**: distance is a recorded
   field, not derived from coordinates, so no rebuild is needed. (Verified
   in critique, not assumed.)
7. Every removal is itemised in provenance (`PII_IDENTITY_REMOVED`,
   `PII_SERIALS_REMOVED`, `PII_BODY_METRICS_REMOVED`,
   `PII_LOCATION_CONCEALED`), with counts.
8. Output re-parsed in `strict` mode (`output_strict_ok`).
9. **CLI**: `chiptime reveal FILE [--json]`; `chiptime scrub FILE -o OUT
   [--gps-radius M] [--drop-all-gps] [--keep-identity] [--keep-serials]
   [--keep-body-metrics]`.

## Acceptance Criteria
- [ ] `reveal` on a real file reports location + serials + any body metrics present,
      and never prints coordinates at more than 2 decimal places by default
- [ ] `scrub` removes identity/serials/body metrics by default; the output no longer
      discloses them (asserted by running `reveal` on the *output*)
- [ ] `--gps-radius` nulls positions near both endpoints while preserving mid-route
      positions and all non-position fields on the same records
- [ ] Nulled positions re-decode as `None`, never `0` (round-trip through the encoder)
- [ ] Distance/duration totals are byte-for-byte unchanged by a location scrub
- [ ] `output_strict_ok` true; passes `validate --platform garmin-connect` where input did
- [ ] Determinism: identical scrub twice → byte-identical output
- [ ] Scrubbing a file with no PII is a no-op that says so, not a silent rewrite

## Public API Impact
- **New**: `chiptime.scrub`, `chiptime.reveal`, `ScrubResult`, `PrivacyReport`;
  CLI verbs `scrub` and `reveal`; four provenance codes.
- **Canonical JSON schema**: unchanged.

## Architectural Placement
`python/src/chiptime/privacy.py`, write layer beside `edit.py`/`trim.py`.
`reveal` is read-only and shares the category tables with `scrub` so the two
can never disagree about what counts as personal.

## Proposed Approach
1. One **category table**: category → (messages, fields) it covers. Both
   verbs read it; `reveal` reports, `scrub` removes. Single source of truth.
2. Location: convert semicircles to degrees, haversine against the first and
   last valid fix, null within radius.
3. Re-encode via F12; strict self-check.

## Dependencies
- **Depends on:** F3 decode, F12 encoder, F11 CLI, ADR-0007 (PII policy)
- **Depended on by:** M3 (TS twin), potential in-browser tool (client-side scrubbing)

## Critique & Assessment

### Necessity — PASS, and the strongest of the M2.8 set
The only job in the research with **no incumbent**: croppers and mergers
exist everywhere, one-click sanitisers do not, and "what does this file
reveal about me" has no answer at all. It also fits chiptime's temperament
better than any competitor feature could — the library already treats
honesty about data as its organising principle, and ADR-0007 already made
this call internally for the corpus. F28 extends the same stance to users'
own files.

### Placement — PASS
Write layer beside `edit`/`trim`. `reveal` is read-only and shares the
category table with `scrub`, so the two can never disagree about what counts
as personal — the failure mode that would matter most (a report that says
"clean" while the scrubber knows better).

### Empirical validation (run during critique)
Audited the private real-file tier and round-tripped nulled positions:

| Claim | Result |
|---|---|
| Nulled positions re-decode as `None`, not `0` | **✓ verified** — contract #4 holds through the encoder |
| Location scrubbing leaves totals untouched | **✓ verified** — elapsed unchanged; distance is a recorded field, not derived from coordinates, so no rebuild is needed |
| Serials live in `file_id` **and** `device_info` | **✓ confirmed in real files** |
| Summary messages carry start/end coordinates | **✓ confirmed** — one real file exposes `start_position_*` on both `lap` and `session`, so scrubbing records alone would have left home coordinates in plain sight |

### ⚠ Correction to the spec's framing
The same audit found that **`user_profile` and `zones_target` are absent
from all three real activity files** — identity and body metrics travel in
*settings* files far more often than in activities. The feature is still
right, but the documentation must not imply every file leaks your weight.
`reveal` reports what is actually present and says so plainly when a
category is clean; marketing copy follows the same rule.

### ⛔ Required change — radius must be distance-based over *all* records
An implementation that nulls only leading and trailing records would leak
the very thing it claims to hide: a loop ride that passes the house
mid-route, or an out-and-back that touches home at the turnaround. The rule
is **"within R metres of either endpoint, wherever it appears in the ride"** —
which also gives Strava-style privacy-zone behaviour for free.

### Risks
- **Whole-activity concealment**: a large radius on a small activity (track
  session, treadmill loop) can null every position. Detect and warn rather
  than silently return a GPS-less file.
- **Distance/speed remain** on scrubbed records — someone determined could
  still infer a route shape from them. Honest documentation, not a false
  promise of anonymity: the feature removes disclosed coordinates, it does
  not make a file untraceable.
- **Blast radius**: additive module; no shared-code changes.

### Contract check
- Silent loss: every removal itemised in provenance with counts; `reveal`
  exists precisely so the user knows what will go before it goes.
- Determinism: category tables are static, haversine is pure arithmetic on
  decoded values; no clock, no randomness.
- Sentinels: nulled positions encode as FIT *invalid* (verified above), never
  zero — "no reading" must not become "the equator".
- Modes: inherited from the read.
- Errors: coded, with suggestions.
- Corpus: no new taxonomy claims; assertions reuse committed cases plus the
  private tier (which carries genuine coordinates).

### Simplification
- **Cut**: configurable coordinate precision in `reveal`. Two decimals
  (~1.1 km, neighbourhood level) is the safe default and the only one worth
  shipping; an exact-coordinates flag would exist mainly to be misused in a
  forum paste. BACKLOG if a real workflow needs it.
- **Cut**: scrubbing arbitrary user-named fields. Categories are the useful
  abstraction; a field-level escape hatch is speculative.
- The 20%/80% version is `reveal` + default metadata scrub + `--gps-radius`,
  which is what remains.

### Final decision: **APPROVE** — conditional on the distance-based radius rule

## Related
- ADR: [0007](../architecture/adrs/0007-real-file-pii-policy.md) (the corpus-side PII stance this extends to user files)
- Implementation: `docs/implementation/f28-privacy-scrub.md`
