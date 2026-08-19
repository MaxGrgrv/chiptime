# Sport Metrics Domain — how each sport measures itself

> M2.7 design foundation, 2026-08-18. Written from established sports-science
> conventions; cross-checked against a platform survey (agent report appended
> as deltas when it lands). Everything here must hold under chiptime's
> contracts: deterministic, null-honest, nothing fabricated.

## 0. The organizing insight

Every endurance sport has ONE **primary intensity signal**, and everything
else hangs off it. Get that mapping right and analytics generalize; get it
wrong and you show cyclists their pace and swimmers their watts.

| Sport | Primary intensity | Pacing display | Secondary | Distance truth |
|---|---|---|---|---|
| Running | pace (from speed) | **min/km** (or min/mi) | HR, cadence (spm), running power (Stryd dev field) | GPS or footpod |
| Cycling | **power (W)** when present, else speed | km/h (speed, never "pace") | HR, cadence (rpm), speed | wheel sensor > GPS |
| Pool swim | pace per 100 | **min/100m** (or /100yd) | SWOLF, stroke rate/count, stroke type | lengths × pool size — NEVER GPS |
| Open-water swim | pace per 100 m | min/100m | stroke rate, HR (often absent) | GPS (noisy; see taxonomy #56) |
| Rowing (erg/OTW) | pace per 500 m ("split") | **min/500m** | stroke rate (spm), watts (split↔W interconvertible) | erg meters or GPS |
| XC skiing | pace or speed by discipline | min/km (classic), km/h common | HR, cadence | GPS |
| Triathlon/multisport | per-leg primary | per-leg convention | transitions as first-class | per-leg |
| Strength | none continuous | n/a | sets × reps × weight, rest time | n/a |
| Hike/walk | pace + vertical | min/km + m/h ascent rate | HR, grade | GPS |

Two corollaries chiptime must encode:
1. **Pace is an inverse**: averaging pace directly is wrong; you average speed
   (or total time / total distance) and *display* as pace. All internal math
   stays in m/s; formatting is the last step.
2. **"Moving" vs "elapsed" is sport-relative**: cyclists coast at 0 W but are
   moving; swimmers rest at the wall inside the elapsed window; runners at a
   traffic light are stopped. We already derive elapsed/timer/moving (ADR-0005)
   — analytics must pick the right denominator per metric (pace uses moving;
   load uses timer; "workout duration" uses elapsed).

## 1. Running

- **Pacing**: seconds-per-km internally; format `M:SS /km`. Splits per km
  (or mile) are the universal single-workout view; "fastest km", negative vs
  positive split (2nd half vs 1st half pace ratio) are the headline insights.
- **Cadence trap** (taxonomy #66): FIT `cadence` on runs is strides/min of
  one leg on many devices; display convention is steps/min (×2 when the
  source is per-leg; `fractional_cadence` adds the half-step). Detection:
  running cadence < 130 ⇒ per-leg convention, double for display —
  heuristic, must be labeled.
- **Efficiency/decoupling** (published, Friel/Coggan-popularized concepts,
  generic math): efficiency = speed/HR; **aerobic decoupling** = (EF first
  half − EF second half)/EF first half; >5% suggests aerobic fatigue. Pure
  arithmetic on our streams; safe naming: `hr_drift_pct`.
- **Grade-adjusted pace**: Minetti energy-cost-of-gradient polynomial is the
  published basis; platform implementations diverge. BACKLOG (needs care),
  but ascent/descent per split ships now.
- **Intervals**: track workouts = laps (button or structured-workout steps);
  fartlek/unstructured = detected speed steps. Running power (Stryd) when
  present behaves like cycling power.

## 2. Cycling

- **Power is truth** when a meter is present: pace is meaningless downhill,
  HR lags. Headline set: avg/max power, **weighted power** (30 s rolling
  mean → 4th-power mean — the published Coggan-style weighting; we use the
  neutral name `weighted_avg_power`), work kJ (∑W·dt/1000), variability
  (`weighted/avg` ratio), best-power curve (5s/1min/5min/20min/60min).
- **Zero vs null is doctrine here** (taxonomy #64): coasting 0 W is REAL and
  belongs in averages; dropout null does not. This is why the parser's
  distinction exists — analytics inherits it for free.
- **Threshold-relative**: with user FTP: intensity ratio (weighted/FTP), zone
  time (Coggan 7-zone default), load score = duration_h × intensity² × 100
  (the classic formula; neutral name `load_score`). Without FTP: report
  absolute numbers only — never estimate FTP from one ride silently.
- **L/R balance** (F22's `right_balance_pct` stream): mean + drift.
- **Intervals**: power steps are sharp (ERG mode literally rectangular —
  taxonomy #89); detection on 10 s-smoothed power works well. Laps often
  meaningless on free rides (auto-lap every 5 km) — `lap_trigger`
  distinguishes button laps (`manual`) from auto-laps.

## 3. Pool swimming

- **Structure IS the data**: lengths → intervals ("sets") → session.
  Distance = lengths × pool_length (never GPS). Pace per 100 from length
  times. SWOLF (strokes + seconds per length) = economy. Stroke type per
  length enables per-stroke stats.
- **Sets detection**: consecutive active lengths with wall-rest below a gap
  threshold (~30 s) form a repeat block; blocks of equal length-count and
  similar pace collapse to "10 × 100m @ 1:45 rest 0:20" — the notation every
  swimmer thinks in. Rest = idle lengths or timestamp gaps at the wall.
- **CSS (critical swim speed)**: published two-distance model
  (400/200: CSS = 200 m / (t400 − t200)); zone anchor if the user supplies
  test times — never inferred from a random session.
- **Drills** (`swim_stroke = drill`) may lack stroke data (taxonomy #73);
  zero-length wall artifacts already flagged (POOL_ZERO_LENGTH).

## 4. Open-water swimming

- min/100m off GPS with humility: taxonomy #56's sighting-zigzag means
  distance runs long. Report both raw and (BACKLOG) smoothed distance;
  stroke rate from cadence-class fields when present. No lengths — interval
  structure only from laps/timer events.

## 5. Rowing

- **Split (/500 m) is the lingua franca**; Concept2's published
  watts↔pace relation (W = 2.80 / pace³ per-meter form; pace = (2.80/W)^⅓
  in s/m) lets us surface both from either. Stroke rate (spm) + distance
  per stroke complete the picture. Erg files (fitness_equipment / rower
  sub-sport) have no GPS; OTW rowing does.

## 6. XC skiing / other endurance

- Discipline-dependent (classic vs skate) pacing; vertical matters
  (ascent rate m/h is the alpine-touring headline). Default treatment:
  generic endurance profile (pace + HR + zones) — correctness over depth.

## 7. Triathlon / multisport

- Already first-class in the model (F9): per-session legs + transitions.
  Analytics = per-leg reports with per-leg conventions + T1/T2 durations +
  total race time. Never blend leg metrics (a "triathlon average pace" is
  meaningless).

## 8. Strength / non-continuous

- `set` messages (sets × reps × weight × exercise category) when present;
  rest-vs-work timeline from set boundaries. Report honestly; no cardio
  metrics forced onto it.

## 9. Load & "more than one workout" (the *and more*)

- **TRIMP** (Banister 1991, published): Σ dt × HRr × 0.64·e^(1.92·HRr)
  (male coefficient variant; documented) where HRr = (HR−rest)/(max−rest).
  Needs resting/max HR from settings or `user_profile`/`zones_target`.
- **Impulse-response fitness/fatigue** (Banister; popularized as
  CTL/ATL/TSB by TrainingPeaks — we use the neutral, now-conventional
  **fitness / fatigue / form**, as intervals.icu does): EWMA of daily load,
  42-day and 7-day time constants; form = fitness − fatigue.
- Load per workout: power-based `load_score` when FTP known; else HR TRIMP;
  else duration-only (flagged as low-confidence). Multi-source consistency
  is a known hard problem — we expose which estimator produced each number.

## 10. Interval detection — the honest algorithm

Requirements: deterministic (contract #2), sport-aware, and honest about
uncertainty (structure is a *reading* of the data, so intervals carry the
evidence basis: `laps:manual`, `steps:workout`, `detected:power-steps`).

1. **Prefer declared structure**: structured-workout `workout_step`s, then
   manual laps (`lap_trigger = manual` — button presses mean intent), then
   swim sets from lengths.
2. **Detected fallback** (bike/run without meaningful laps): primary stream
   → rolling median (11-sample) → threshold bands relative to session
   median of nonzero work (work ≥ 110%, recovery ≤ 85%) → alternating
   segments with min duration 20 s work / 15 s recovery, adjacent merges →
   report only if ≥ 3 work segments with pairwise similarity (duration CV
   < 40%) — otherwise "no clear interval structure", which is a valid
   answer. All constants are named module constants (JS port copies them).
3. **Repeat grouping**: cluster similar work segments (duration within
   ±25%, intensity within ±10%) → "N × duration @ intensity" notation.

## 11. Naming safety (to verify against the survey)

Avoid TrainingPeaks trademarks (NP, TSS, IF, CTL/ATL/TSB as branded terms).
Ours: `weighted_avg_power`, `intensity_ratio`, `load_score`, `fitness` /
`fatigue` / `form`, `hr_drift_pct`, `efficiency`, `swolf`, `trimp`
(published-science name), `css` (published), `split_500m`. Formulas
documented in docstrings with citations — names are ours, math is public.

## 12. Survey deltas (web verification, 2026-08-18)

Naming (verified against USPTO/Justia + vendor pages):
- Registered marks are exactly **TSS / Training Stress Score, NP / Normalized
  Power, IF / Intensity Factor** (TrainingPeaks LLC, 2013 filings; passing to
  Garmin with the July 2026 acquisition). **CTL/ATL/TSB and FTP are NOT
  registered** — but the OSS convention is renamed anyway: Golden Cheetah
  IsoPower/BikeStress/BikeIntensity + LTS/STS/SB (v3.5 "Deprecate
  TrainingPeaks trademarks"), intervals.icu & Strava fitness/fatigue/form +
  weighted-average-power/intensity/load. Marks cover the *names, not the
  math* (published in Training and Racing with a Power Meter). Our names
  (§11) sit squarely on the established safe convention. Sources:
  trainingpeaks.com/learn/articles/glossary-of-trainingpeaks-metrics/,
  trademarks.justia.com/owners/trainingpeaks-llc-4253944, sauce.llc,
  GoldenCheetah wiki FAQ-METRICS, the5krunner.com/2026/07/22/.
- FTP as a term is unregistered and used freely industry-wide → `ftp_w` in
  AthleteSettings is fine.

Interval detection in the wild (validates §10's design):
- **intervals.icu** (David Tinker, forum breadcrumbs; no full pseudocode
  published): detection is *power-only*, keyed on sharp edges in smoothed
  power, with spike-suppression heuristics; HR/pace activities fall back to
  laps; per-zone minimum durations + minimum rep counts gate HR intervals
  (e.g. Z4 ≥ 110 s min 4 reps, Z5 ≥ 25 s min 4). Structured-workout laps
  map via `wkt_step_index` — and that linkage is *lost when a file
  round-trips through Strava*. Single-lap activities ignore laps and
  auto-detect. Non-work segments become recovery intervals.
- **Garmin**: no post-hoc detection at all — laps are authoritative
  (manual button / Auto Lap / one per workout step, with `lap_trigger`
  recording why). **Strava**: no detection either; Workout Analysis needs
  ≥ 2 recorded laps, else runs get fixed 1 km/1 mi splits.
- Consequence for F24: our ladder (workout steps → manual laps → swim sets
  → band-based detection on the primary stream, with min-duration and
  min-rep gates and an honest "no clear structure" result) is the union of
  what the platforms do, done deterministically.
