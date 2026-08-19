---
description: Sport-aware workout analytics from FIT files: pace and splits, interval detection with evidence, training load, and machine-readable insights.
---

# Analyze workouts

The analytics layer turns honest streams into meaning — in each sport's own language.
It is optional (`chiptime.metrics`), deterministic, and never estimates what it
wasn't given.

## The one-call version

```bash
chiptime analyze ride.fit --ftp 250 --max-hr 185 --resting-hr 48
```

```text
session 1: cycling/virtual_activity
  55:11 · 29.61 km · 32.2 km/h (moving) · avg 164 W · weighted 175 W · avg HR 136
  structure [laps:manual]: 3 x 10:00 @ 194 W rest 3:24
  load 45 [power+ftp]
  PACING_NEGATIVE_SPLIT: Second half 7.6% faster than the first.
```

Add `--json` for the machine-readable report.

## Sports speak differently

| Sport | Pacing | Primary signal |
|---|---|---|
| Running | min/km | pace (power if a running power stream exists) |
| Cycling | km/h | **watts** when a power meter is present |
| Pool swim | min/100m + SWOLF | pace from lengths × pool size — never GPS |
| Open water | min/100m | GPS pace (with its known optimism) |
| Rowing | /500m split | watts ↔ split via the Concept2 relation |

A sport-profile registry routes every session; unknown sports get an honest generic
treatment rather than a wrong specific one.

```python
from chiptime import metrics

profile = metrics.profile_for(session)     # SportProfile(key="pool_swim", pace_style="per_100m", ...)
metrics.format_pace(105.0, "per_100m", suffix=True)    # "1:45/100m"
metrics.watts_to_split_500m(200)                       # 120.7 → a 2:00.7 split
```

Pace is treated as *presentation*: all math happens in m/s and seconds, because
averaging paces directly is a classic error (pace is an inverse).

## Intervals: an evidence ladder

`detect_structure` reads workout structure the way athletes think in it — and every
result names its evidence:

```python
st = metrics.detect_structure(session, result.messages)
st.basis            # "steps:workout" | "laps:manual" | "lengths:sets"
                    # | "detected:power-steps" | "detected:speed-steps" | "none"
st.repeats[0].label # "6 x 0:30 @ 300 W rest 0:30"
st.note             # when basis == "none": WHY (too few reps, too varied, ...)
```

The ladder: structured-workout steps → manual lap presses → swim sets grouped from
lengths → deterministic detection on smoothed power/speed. Detection refuses to
hallucinate: fewer than 3 similar work efforts, or wildly varied durations, and the
answer is `none` *with the reason* — a valid result, not a failure.

## Thresholds are yours, never guessed

```python
settings = metrics.AthleteSettings(
    ftp_w=250, max_hr=185, resting_hr=48,
    hr_zone_bounds=(115, 135, 155, 172, 188),
)
report = metrics.analyze(result, settings)
```

Zones and load come from your settings or from zone messages inside the file —
**never** estimated from the workout itself. Without inputs, the report says exactly
what was omitted and why:

```python
report.sessions[0].omissions
# ["load: hr covers only 17% of the session (< 50%); trimp would understate load"]
```

## Load, named

Every load number carries its basis: `power+ftp` (duration × intensity² × 100, from
4th-power-weighted watts), or `hr-trimp` (Banister TRIMP, sex-labeled coefficient) —
with an HR-coverage guard so a swim that only logged HR at the wall can't produce a
confidently wrong number. For trends, `fitness_fatigue_form()` runs the classic
42-day / 7-day impulse-response over your daily loads.

## Insight codes

Notable observations come with stable codes and numeric evidence — built for both
humans and agents:

| Code | Fires when |
|---|---|
| `PACING_NEGATIVE_SPLIT` / `PACING_POSITIVE_SPLIT` | halves differ by > 2% |
| `HR_DRIFT_HIGH` | output per heartbeat fell > 5% (aerobic decoupling) |
| `COASTING_HIGH` | > 25% of ride samples at 0 W |
| `WORKOUT_STRUCTURE` | repeated intervals found (label in evidence) |
