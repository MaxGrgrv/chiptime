# Changelog

## 0.5.0 — 2026-08-21 (M2.8: file surgery begins)

- **New: `chiptime edit`** — change what a file *says about itself* and keep
  it uploadable. Sport/sub-sport (applied everywhere they are declared, so a
  file can't contradict itself), recording-device identity (`file_id` + the
  creator `device_info` entry only), and signed time shifts across every
  profile-typed timestamp. Every edit lands in `provenance[]`; the output is
  re-parsed in strict mode before you see it (`output_strict_ok`).
- **Honest by construction**: `sub_sport` is never inferred from `sport` —
  changing sport while a specific sub-sport remains emits
  `SPORT_PAIR_IMPLAUSIBLE` instead of guessing. Time shifts that would leave
  the representable range, or land on the invalid sentinel, refuse the whole
  edit and write no bytes.
- **Everything unnamed round-trips untouched** — unknown messages, unknown
  enum values, and developer fields survive an unrelated edit, asserted
  field-by-field in tests.
- **New corpus case** `protocol/unknown-enum-values` closes a real coverage
  gap: taxonomy #24 (unknown enums pass through as raw values) had no case.
- PRD non-goals corrected: the sport rule now separates inference (still
  forbidden) from user-directed edits; the analytics non-goal superseded by
  M2.7 was fixed.

## 0.4.2 — 2026-08-21

- **Fixed**: `repair` raised `EncodeError` on files whose field 253 was
  declared `byte[4]` and reassembled during decode (the Xiaomi-pipeline
  class, taxonomy #17/#88) — such files could not be repaired at all.
  Reassembled fields now re-emit in canonical numeric form (ADR-0006)
  instead of replaying the source encoder's mistake.
- **Added**: identity round-trip gate — every corpus case (including the
  real-file tier, up to ~73k messages) must survive parse → re-encode →
  parse with every field value intact. This is the foundation the write
  verbs stand on.

## 0.4.1 — 2026-08-19

- Verified on Python 3.14 (full suite, strict typing, byte-identical
  corpus output); classifiers and CI matrix now cover 3.11–3.14.
  `requires-python >=3.11` is unchanged — newer Pythons were never
  blocked, the metadata just lagged.

## 0.4.0 — 2026-08-18 (M2.7: analytics layer)

`chiptime.metrics` grows from a module into the analytics package (ADR-0008):
optional, zero-dep, never imported by the core, deterministic, trademark-safe
names, thresholds only ever from the user or the file.

- **Sport profiles + pacing (F23)**: profiles-as-data registry (running /
  cycling / pool & OW swim / rowing / hiking / XC / generic), primary-signal
  resolution, labeled per-leg cadence doubling; inverse-safe pace math
  ("4:20/km", "1:52.5/500m"), Concept2 watts↔split, boundary-interpolated
  distance splits, moving→timer→elapsed pace ladder with basis strings;
  `AthleteSettings` + zone ladder (settings > in-file zone messages > omitted).
- **Interval & structure detection (F24)**: evidence ladder — workout steps
  (`wkt_step_index` + step intensity) → manual laps (≥2, `lap_trigger`) →
  swim sets (wall-rest grouping × pool length) → deterministic band detection
  (rolling median, quantile-midpoint reference, hysteresis, spike guard,
  rep-count + duration-CV honesty gates) → `none` with a reason. Repeats in
  athlete notation: "6 x 0:30 @ 300 W", "4 x 100m @ 1:44/100m rest 0:20".
- **Insights + load + CLI (F25)**: per-session `WorkoutReport` (pace/speed with
  basis, weighted_avg_power, variability ratio, work kJ, power curve, SWOLF,
  splits, structure, zone time, load) + machine-readable insight codes
  (PACING_NEGATIVE/POSITIVE_SPLIT, HR_DRIFT_HIGH, COASTING_HIGH,
  WORKOUT_STRUCTURE) with numeric evidence; load ladder power+ftp → hr-trimp
  (Banister, sex-labeled coefficient, ≥50% HR-coverage guard — sparse swim HR
  can no longer silently understate) → honest omission; fitness/fatigue/form
  EWMA (42 d/7 d); `chiptime analyze FILE [--json] [--ftp …]`.
- Verified names against USPTO/vendor records: exactly TSS/NP/IF are
  trademarked; fitness/fatigue/form + weighted-average-power are the OSS
  convention (research doc §12).
- Repo-wide `ruff format` adopted and enforced in the pre-push hook + CI.

## 0.3.0 — 2026-08-18 (M2.5: real-world hardening)

Validated against 66 real device files (Wahoo ROAM, pool/OW swims, a 5-session
IRONMAN, courses, workouts, monitoring) — zero contract violations throughout.

- **Real-file soak fixes**: FIT_NO_CONTENT for valid-but-empty shells (#16,
  found in the wild); repair drops impossible local_timestamp (GC-invalid
  repairs 4→0); sport-aware + run-length-based DISTANCE_FROZEN (false
  positives → 0, dead-sensor detection intact).
- **Full profile**: generated from the FIT SDK — 119 messages / 1,382 fields /
  176 enums, every field verified against an independent implementation;
  high-unknown files 9 → 0.
- **Real-file corpus tier** (ADR-0007): git-ignored private cases with
  promotion tooling; six real files pinned locally; PII policy set.
- **Performance**: 1.72× (1.04 MB in 599 ms; bit-identical output), CRC-256,
  decode plans, fast ISO; next multiple BACKLOG'd as architecture.
- **HRV + analytics foundation**: Activity.hrv_intervals_s (#72);
  `chiptime.metrics` (mean-max curves, dt-capped zone time, SWOLF —
  null-honest by construction); `Records.to_pandas()` via `chiptime[pandas]`.

## 0.2.0 — 2026-08-18 (M2: the repair release)

- **Encoder** (ADR-0006): canonical FIT writer — lossless re-emit of anything
  decoded (unknown messages, developer fields, big-endian sources) + profile
  synthesis; re-encoded files pass strict mode.
- **`chiptime repair`**: salvage → synthesize missing file_id/events/lap/
  session/activity → valid .fit, with REPAIR_* provenance and honest refusal
  when nothing is salvageable. The Zwift-crash class repairs to a
  Garmin-Connect-valid file.
- **`chiptime validate --platform strict-spec|garmin-connect|strava`**:
  platform acceptance as named heuristic checks (#99/#102).
- **CRC triage**: mismatches diagnosed (unterminated write / storage damage /
  in-place corruption).
- **Tier-2 depth**: compressed_speed_distance expansion (12-bit rollover),
  accumulator unwrap, event subfields (timer_trigger), HR/power/distance/
  pool/lap plausibility flags — flagged, never edited.
- **Robustness gate**: every corpus case — including deliberately corrupt,
  truncated, and wrapped files — decodes without a crash (3279 messages
  across 63 cases).

## 0.1.0 — 2026-08-18 (M1)

First release. Python, zero runtime dependencies.

- **Decode**: crash-proof frame reader (defects-as-values), all base types, both
  endiannesses, compressed timestamps with rollover + anchor recovery, developer
  fields incl. every malformed variant, unknown-everything preserved.
- **Recovery** (OSS-first): mid-file resynchronization, preamble-garbage skip,
  truncation salvage with estimates — every skipped byte accounted.
- **Intake**: gzip/zip unwrap, chained files, content sniffing with named formats.
- **Semantics**: Activity/Session model, columnar streams (0 ≠ null, per-stream
  sparsity), enhanced-pair reconciliation, timer state machine, classified gaps,
  declared-vs-derived discrepancies, session rebuild, multisport, GPS plausibility
  gates with virtual-world exemption.
- **Modes**: strict / lenient / forensic (forensic never drops).
- **Output**: RFC 8785 canonical JSON, byte-identical across runs/processes/OSes;
  typed errors with suggestions; provenance for every repair.
- **Conformance corpus**: 56 golden cases covering all 18 Tier-1 taxonomy items.
- **CLI**: `chiptime parse|inspect|codes` with agent exit codes (0/2/3/4/64).
