/**
 * Declared-vs-derived reconciliation (#92), sanity flags (#93/#97), ascent/descent
 * derivation. Discrepancies are exposed, never auto-corrected.
 *
 * Twin of `python/src/chiptime/semantics/reconcile.py`.
 *
 * Every diagnostic here interpolates numbers into prose, which is where the port's
 * recurring hazard lives: `pyFixed` and `pyFloatStr` exist because `toFixed` rounds
 * half away from zero and `String(55)` drops the `.0` that Python prints.
 */

import type { Diagnostic } from "../errors.js";
import { type Session, type Totals, getStream, recordCount } from "../model.js";
import { pyFixed, pyFloatStr } from "../numeric.js";

const ASCENT_HYSTERESIS_M = 3.0;
const HR_CEILING_BPM = 230.0;
const HR_FLATLINE_S = 120;
const POWER_CEILING_W = 2500.0;
const LAP_COVERAGE_MIN = 0.9;
const FROZEN_MIN_RUN = 30; // consecutive records (F19 real-ride finding)
const FROZEN_SPEED_FLOOR = 2.0; // m/s: above walking pace

/** field -> [absolute floor, relative band] */
const TOTALS_TOL: [keyof Totals, number, number][] = [
  ["elapsedTimeS", 2.0, 0.02],
  ["timerTimeS", 2.0, 0.02],
  ["distanceM", 10.0, 0.02],
  ["ascentM", 10.0, 0.15],
  ["descentM", 10.0, 0.15],
];
/** The canonical field names, for discrepancy reporting. */
const TOTALS_FIELD_NAME: Readonly<Record<string, string>> = {
  elapsedTimeS: "elapsed_time_s",
  timerTimeS: "timer_time_s",
  distanceM: "distance_m",
  ascentM: "ascent_m",
  descentM: "descent_m",
};
const AVGMAX_TOL: [string, number, number][] = [
  ["heart_rate", 2.0, 0.03],
  ["power", 5.0, 0.05],
  ["speed", 0.2, 0.03],
  ["cadence", 2.0, 0.05],
];

export function deriveAscentDescent(s: Session): void {
  const alt = getStream(s.records, "altitude");
  if (alt === undefined) return;
  let up = 0;
  let down = 0;
  let ref: number | null = null;
  for (const v of alt.values) {
    if (typeof v !== "number") continue;
    if (ref === null) {
      ref = v;
      continue;
    }
    const d = v - ref;
    if (d >= ASCENT_HYSTERESIS_M) {
      up += d;
      ref = v;
    } else if (d <= -ASCENT_HYSTERESIS_M) {
      down += -d;
      ref = v;
    }
  }
  if (ref !== null) {
    s.derived.ascentM = up;
    s.derived.descentM = down;
  }
}

export function reconcile(s: Session, warnings: Diagnostic[], scope: string): void {
  const d = s.declared;
  if (d === null) return;

  for (const [key, floor, rel] of TOTALS_TOL) {
    compare(
      s,
      TOTALS_FIELD_NAME[key as string] as string,
      d[key] as number | null,
      s.derived[key] as number | null,
      floor,
      rel,
    );
  }
  for (const [key, floor, rel] of AVGMAX_TOL) {
    compare(s, `avg.${key}`, d.avg.get(key) ?? null, s.derived.avg.get(key) ?? null, floor, rel);
    compare(s, `max.${key}`, d.max.get(key) ?? null, s.derived.max.get(key) ?? null, floor, rel);
  }

  const shared = [...d.avg.keys()].filter((k) => d.max.has(k)).sort();
  for (const key of shared) {
    const a = d.avg.get(key) as number;
    const m = d.max.get(key) as number;
    if (a > m) {
      warnings.push({
        code: "SUMMARY_AVG_EXCEEDS_MAX",
        detail: `declared avg ${key} (${pyFloatStr(a)}) exceeds declared max (${pyFloatStr(m)}) — summary untrustworthy (taxonomy #93)`,
        scope,
      });
    }
  }
  const negChecks: [keyof Totals, string][] = [
    ["elapsedTimeS", "elapsed_time_s"],
    ["timerTimeS", "timer_time_s"],
    ["distanceM", "distance_m"],
    ["caloriesKcal", "calories_kcal"],
  ];
  for (const [key, name] of negChecks) {
    const v = d[key] as number | null;
    if (v !== null && v < 0) {
      warnings.push({
        code: "SUMMARY_NEGATIVE_TOTAL",
        detail: `declared ${name} is negative (${pyFloatStr(v)})`,
        scope,
      });
    }
  }

  const n = recordCount(s.records);
  if (d.elapsedTimeS === 0 && n > 0) {
    warnings.push({
      code: "ZERO_DURATION_SESSION",
      detail: `session declares zero duration but contains ${n} record(s) (taxonomy #97)`,
      scope,
    });
  }
  const avgSpeed = s.derived.avg.get("speed");
  const derDist = s.derived.distanceM;
  if (n > 0 && avgSpeed !== undefined && avgSpeed > 1.0 && (derDist === null || derDist < 1.0)) {
    warnings.push({
      code: "MOVEMENT_WITHOUT_DISTANCE",
      detail: `speed stream averages ${pyFixed(avgSpeed, 1)} m/s but the distance stream never advances (taxonomy #97; dead distance source?)`,
      scope,
    });
  }
}

/**
 * HR/power physiological gates (#62/#63) and distance anomalies (#59).
 * Flags only — interpolation is opt-in repair territory (BACKLOG).
 */
export function sensorFlags(s: Session, warnings: Diagnostic[], scope: string): void {
  const hr = getStream(s.records, "heart_rate");
  if (hr !== undefined) {
    let high = 0;
    for (const v of hr.values) if (typeof v === "number" && v > HR_CEILING_BPM) high++;
    if (high) {
      warnings.push({
        code: "HR_IMPLAUSIBLE",
        detail: `${high} heart-rate sample(s) above ${pyFixed(HR_CEILING_BPM, 0)} bpm (strap static / contact class, #62)`,
        scope,
      });
    }
    let run = 0;
    let best = 0;
    let prev: unknown = null;
    for (const v of hr.values) {
      if (v !== null && v !== undefined && v === prev) {
        run += 1;
        if (run > best) best = run;
      } else {
        run = 0;
      }
      prev = v;
    }
    if (best >= HR_FLATLINE_S) {
      warnings.push({
        code: "HR_FLATLINE",
        detail: `heart rate flatlined for ${best + 1} consecutive record(s) (#62)`,
        scope,
      });
    }
  }

  const power = getStream(s.records, "power");
  if (power !== undefined) {
    let high = 0;
    for (const v of power.values) if (typeof v === "number" && v > POWER_CEILING_W) high++;
    if (high) {
      warnings.push({
        code: "POWER_IMPLAUSIBLE",
        detail: `${high} power sample(s) above ${pyFixed(POWER_CEILING_W, 0)} W (#63); flagged, not removed — sprints are real`,
        scope,
      });
    }
  }

  const dist = getStream(s.records, "distance");
  if (dist === undefined) return;
  const vals: [number, number][] = [];
  dist.values.forEach((v, i) => {
    if (typeof v === "number") vals.push([i, v]);
  });
  let decreases = 0;
  let resets = 0;
  for (let k = 1; k < vals.length; k++) {
    const a = (vals[k - 1] as [number, number])[1];
    const b = (vals[k] as [number, number])[1];
    if (b < a) {
      if (b < 1.0 && a > 10.0) resets++;
      else decreases++;
    }
  }
  if (decreases) {
    warnings.push({
      code: "DISTANCE_DECREASES",
      detail: `distance stream decreases ${decreases} time(s) (#59)`,
      scope,
    });
  }
  if (resets) {
    warnings.push({
      code: "DISTANCE_RESET",
      detail: `distance stream resets to zero ${resets} time(s) mid-activity (#59)`,
      scope,
    });
  }

  const speed = getStream(s.records, "speed");
  // Swims legitimately freeze distance between lengths/fixes (#56/#73); everywhere
  // else, only a LONG consecutive run at real speed is a dead sensor — short freezes
  // at ~1 m/s are ride starts and junctions (F19 finding on a real Wahoo ROAM ride:
  // 3 runs, max 12 s, all benign).
  if (speed !== undefined && vals.length >= 2 && s.sport !== "swimming") {
    let run = 0;
    let longest = 0;
    for (let k = 1; k < vals.length; k++) {
      const d0 = (vals[k - 1] as [number, number])[1];
      const [i1, d1] = vals[k] as [number, number];
      const v = speed.values[i1];
      if (d1 === d0 && typeof v === "number" && v > FROZEN_SPEED_FLOOR) {
        run += 1;
        if (run > longest) longest = run;
      } else {
        run = 0;
      }
    }
    if (longest >= FROZEN_MIN_RUN) {
      warnings.push({
        code: "DISTANCE_FROZEN",
        detail: `distance frozen for ${longest} consecutive record(s) while moving faster than ${pyFloatStr(FROZEN_SPEED_FLOOR)} m/s (dead distance source, #59)`,
        scope,
      });
    }
  }
}

/** Pool-swim semantics (#73): lengths x pool size vs declared distance. */
export function swimChecks(s: Session, warnings: Diagnostic[], scope: string): void {
  if (s.lengths.length === 0) return;
  let zero = 0;
  for (const ln of s.lengths) {
    if (ln.lengthType === "active" && ln.totalElapsedTimeS !== null && ln.totalElapsedTimeS < 2.0) {
      zero++;
    }
  }
  if (zero) {
    warnings.push({
      code: "POOL_ZERO_LENGTH",
      detail: `${zero} active length(s) under 2 s (wall push-off artifacts, #73)`,
      scope,
    });
  }
  let active = 0;
  for (const ln of s.lengths) if (ln.lengthType === "active") active++;
  if (active && s.declared !== null && s.declared.distanceM) {
    const implied = s.declared.distanceM / active;
    if (!(implied >= 15.0 && implied <= 55.0)) {
      warnings.push({
        code: "POOL_LENGTH_IMPLAUSIBLE",
        detail: `declared distance / ${active} active lengths implies a ${pyFixed(implied, 1)} m pool (mis-set pool size class, #73 — flaggable, not fixable)`,
        scope,
      });
    }
  }
}

/** Lap defects (#94): zero duration, coverage gaps. */
export function lapChecks(s: Session, warnings: Diagnostic[], scope: string): void {
  let zero = 0;
  for (const lap of s.laps) {
    if (lap.declared !== null && lap.declared.elapsedTimeS === 0) zero++;
  }
  if (zero) {
    warnings.push({
      code: "LAP_ZERO_DURATION",
      detail: `${zero} zero-duration lap(s) (double lap-button press, #94)`,
      scope,
    });
  }
  if (s.laps.length > 0 && s.derived.elapsedTimeS) {
    let covered = 0;
    for (const lap of s.laps) {
      if (lap.declared !== null) covered += lap.declared.elapsedTimeS ?? 0;
    }
    if (covered < LAP_COVERAGE_MIN * s.derived.elapsedTimeS) {
      warnings.push({
        code: "LAP_COVERAGE_GAP",
        detail: `laps cover ${pyFixed(covered, 0)}s of a ${pyFixed(s.derived.elapsedTimeS, 0)}s session (#94)`,
        scope,
      });
    }
  }
}

function compare(
  s: Session,
  fname: string,
  dec: number | null,
  der: number | null,
  floor: number,
  rel: number,
): void {
  if (dec === null || der === null) return;
  const delta = der - dec;
  if (Math.abs(delta) > Math.max(floor, rel * Math.abs(dec))) {
    s.discrepancies.push({ field: fname, declared: dec, derived: der, delta });
  }
}
