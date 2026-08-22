/**
 * chiptime/metrics — optional analytics on chiptime's honest streams.
 *
 * Twin of `python/src/chiptime/metrics/__init__.py`. Import explicitly
 * (`chiptime/metrics`); the core never imports this package. Everything inherits
 * the streams' guarantees: sentinels are already null, zero is real (taxonomy
 * #64). Names are generic on purpose (ADR-0008 §7).
 */

export {
  MEAN_MAX_MIN_COVERAGE,
  meanMax,
  swolf,
  timeInZones,
  ZONE_DT_CAP_S,
} from "./basics.js";
export type { ActivityReport, Insight, WorkoutReport } from "./insights.js";
export {
  analyze,
  analyzeSession,
  COASTING_SHARE_PCT,
  dumpsReportJson,
  HR_DRIFT_PCT,
  INSIGHT_CODES,
  reportToPlain,
  SPLIT_DELTA_PCT,
} from "./insights.js";
export type { Interval, IntervalStructure, RepeatGroup } from "./intervals.js";
export {
  detectStructure,
  MAX_DURATION_CV,
  MIN_WORK_REPS,
  RECOVERY_BAND,
  SWIM_SET_REST_MIN_S,
  WORK_BAND,
} from "./intervals.js";
export type { FitnessPoint, LoadEstimate } from "./load.js";
export {
  FATIGUE_TC_DAYS,
  FITNESS_TC_DAYS,
  fitnessFatigueForm,
  hrCoverageFraction,
  intensityRatio,
  loadScore,
  TRIMP_K_FEMALE,
  TRIMP_K_MALE,
  TRIMP_MIN_COVERAGE,
  trimp,
  WEIGHTED_POWER_WINDOW,
  weightedAvgPower,
  workKj,
  workoutLoad,
} from "./load.js";
export type { Split } from "./pacing.js";
export {
  CONCEPT2_COEFF,
  distanceSplits,
  formatPace,
  formatSpeedKmh,
  paceSeconds,
  sessionPaceS,
  speedFromPace,
  split500mToWatts,
  wattsToSplit500m,
} from "./pacing.js";
export type { AthleteSettings } from "./settings.js";
export type { PaceStyle, SportProfile } from "./sports.js";
export {
  cadenceDisplay,
  primarySignal,
  profileFor,
  RUN_PER_LEG_CADENCE_MAX,
} from "./sports.js";
export { hrZoneBounds, powerZoneBounds } from "./zones.js";
