---
description: chiptime.metrics API: analyze, detect_structure, pacing, splits, zones, and load estimators with explicit evidence bases.
---

# Python API — metrics

The optional analytics package: `from chiptime import metrics`. Never imported by
the core; everything is a **pure function of the parsed model** plus optional
[`AthleteSettings`][chiptime.metrics.settings.AthleteSettings] — no state, no
network, no wall clock, deterministic to the byte.

## The mental model

```text
analyze(result, settings) ──► ActivityReport ──► [WorkoutReport per session]
   │
   │   composes public pieces you can also call directly:
   ├─ profile_for(session)          which sport language to speak
   ├─ primary_signal(session)       watts or speed, given what exists
   ├─ distance_splits(session)      km/mile splits
   ├─ detect_structure(session, messages)   intervals, with evidence
   ├─ time_in_zones(...)            only when zone bounds were provided
   └─ workout_load(session, settings)       power+ftp → hr-trimp → omitted
```

Three rules govern every number that comes out:

1. **Basis strings.** Derived values name their evidence — a load is
   `power+ftp` or `hr-trimp`, structure is `laps:manual` or
   `detected:power-steps`. You always know what a number is standing on.
2. **Omissions over guesses.** Thresholds (FTP, max HR, zones) come from your
   `AthleteSettings` or from messages inside the file — never estimated from
   the workout. Missing inputs produce an entry in `omissions[]`, not a number.
3. **Compose freely.** `analyze` is a convenience over public parts. Only want
   interval detection? Call `detect_structure(session, result.messages)` and
   skip the rest.

## Reports

::: chiptime.metrics.insights.analyze

::: chiptime.metrics.insights.analyze_session

::: chiptime.metrics.insights.WorkoutReport

::: chiptime.metrics.insights.Insight

## Settings & zones

::: chiptime.metrics.settings.AthleteSettings

::: chiptime.metrics.zones.hr_zone_bounds

::: chiptime.metrics.zones.power_zone_bounds

## Sport profiles

::: chiptime.metrics.sports.SportProfile

::: chiptime.metrics.sports.profile_for

::: chiptime.metrics.sports.primary_signal

::: chiptime.metrics.sports.cadence_display

## Pacing & splits

::: chiptime.metrics.pacing.pace_seconds

::: chiptime.metrics.pacing.format_pace

::: chiptime.metrics.pacing.distance_splits

::: chiptime.metrics.pacing.session_pace_s

::: chiptime.metrics.pacing.split_500m_to_watts

::: chiptime.metrics.pacing.watts_to_split_500m

## Intervals

::: chiptime.metrics.intervals.detect_structure

::: chiptime.metrics.intervals.IntervalStructure

::: chiptime.metrics.intervals.Interval

::: chiptime.metrics.intervals.RepeatGroup

## Load

::: chiptime.metrics.load.workout_load

::: chiptime.metrics.load.LoadEstimate

::: chiptime.metrics.load.weighted_avg_power

::: chiptime.metrics.load.trimp

::: chiptime.metrics.load.fitness_fatigue_form

::: chiptime.metrics.load.hr_coverage_fraction

## Basics

::: chiptime.metrics.mean_max

::: chiptime.metrics.time_in_zones

::: chiptime.metrics.swolf
