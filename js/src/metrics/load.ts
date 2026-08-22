/**
 * Training-load estimators — published math, neutral names, explicit basis.
 *
 * Twin of `python/src/chiptime/metrics/load.py`. See that module's docstring for
 * the formula citations (Coggan-style weighting, Banister TRIMP and
 * impulse-response; trademarked *names* avoided per ADR-0008 §7).
 */

import { type Session, getStream } from "../model.js";
import { ZONE_DT_CAP_S } from "./basics.js";
import type { AthleteSettings } from "./settings.js";

export const WEIGHTED_POWER_WINDOW = 30; // samples (record domain; ~30 s at 1 Hz)
export const TRIMP_COEFF = 0.64;
export const TRIMP_K_MALE = 1.92; // used as documented default when sex unset
export const TRIMP_K_FEMALE = 1.67;
export const TRIMP_MIN_COVERAGE = 0.5; // HR must cover >= this fraction of the session
export const FITNESS_TC_DAYS = 42.0;
export const FATIGUE_TC_DAYS = 7.0;

function present(values: readonly unknown[]): number[] {
  return values.filter((v): v is number => typeof v === "number");
}

/**
 * 4th-power-weighted mean over a 30-sample rolling mean. Zeros are real (coasting)
 * and stay in; nulls (dropouts) are skipped, never zero-filled. Null when fewer
 * than one full window of samples is present.
 */
export function weightedAvgPower(values: readonly unknown[]): number | null {
  const vals = present(values);
  const n = vals.length;
  if (n < WEIGHTED_POWER_WINDOW) return null;
  let acc = 0;
  let fourthSum = 0;
  const windowMeans = n - WEIGHTED_POWER_WINDOW + 1;
  for (let i = 0; i < n; i++) {
    acc += vals[i] as number;
    if (i >= WEIGHTED_POWER_WINDOW) acc -= vals[i - WEIGHTED_POWER_WINDOW] as number;
    if (i >= WEIGHTED_POWER_WINDOW - 1) {
      const m = acc / WEIGHTED_POWER_WINDOW;
      fourthSum += m * m * m * m;
    }
  }
  return (fourthSum / windowMeans) ** 0.25;
}

/**
 * Mechanical work: sum W x dt / 1000, dt capped at the gap policy (a recording gap
 * is a gap, not free kilojoules).
 */
export function workKj(
  times: readonly (number | null)[],
  values: readonly unknown[],
): number | null {
  let total = 0;
  let seen = false;
  for (let i = 0; i < times.length - 1; i++) {
    const t0 = times[i];
    const t1 = times[i + 1];
    const v = values[i];
    if (t0 === null || t0 === undefined || t1 === null || t1 === undefined) continue;
    if (typeof v !== "number") continue;
    const dt = t1 - t0;
    if (dt <= 0) continue;
    total += v * Math.min(dt, ZONE_DT_CAP_S);
    seen = true;
  }
  return seen ? total / 1000.0 : null;
}

export function intensityRatio(weightedPower: number, ftpW: number): number {
  return weightedPower / ftpW;
}

export function loadScore(durationS: number, intensity: number): number {
  return (durationS / 3600.0) * intensity * intensity * 100.0;
}

/**
 * Banister TRIMP. `sex` picks the published coefficient (1.92 male / 1.67 female);
 * unset uses the male coefficient — callers surface that in the basis string. Null
 * if the HR reserve is degenerate or no data.
 */
export function trimp(
  times: readonly (number | null)[],
  hrValues: readonly unknown[],
  options: { restingHr: number; maxHr: number; sex?: string | null },
): number | null {
  const { restingHr, maxHr } = options;
  if (maxHr <= restingHr) return null;
  const k = options.sex === "female" ? TRIMP_K_FEMALE : TRIMP_K_MALE;
  const reserve = maxHr - restingHr;
  let total = 0;
  let seen = false;
  for (let i = 0; i < times.length - 1; i++) {
    const t0 = times[i];
    const t1 = times[i + 1];
    const v = hrValues[i];
    if (t0 === null || t0 === undefined || t1 === null || t1 === undefined) continue;
    if (typeof v !== "number") continue;
    const dt = t1 - t0;
    if (dt <= 0) continue;
    let hrr = (v - restingHr) / reserve;
    hrr = hrr < 0 ? 0 : hrr > 1 ? 1 : hrr;
    total += (Math.min(dt, ZONE_DT_CAP_S) / 60.0) * hrr * TRIMP_COEFF * Math.exp(k * hrr);
    seen = true;
  }
  return seen ? total : null;
}

/** A load number that says where it came from (ADR-0008 §5). */
export interface LoadEstimate {
  readonly value: number;
  readonly basis: string;
  readonly components: Readonly<Record<string, number>>;
}

/**
 * Fraction of the session duration covered by present-HR sample pairs. Null when
 * there is no HR stream or no duration to compare against.
 */
export function hrCoverageFraction(session: Session): number | null {
  const hr = getStream(session.records, "heart_rate");
  const dur = sessionDurationS(session);
  if (hr === undefined || !dur) return null;
  let covered = 0;
  const times = session.records.time;
  for (let i = 0; i < times.length - 1; i++) {
    const t0 = times[i];
    const t1 = times[i + 1];
    const v = hr.values[i];
    if (t0 === null || t0 === undefined || t1 === null || t1 === undefined) continue;
    if (typeof v !== "number") continue;
    const dt = t1 - t0;
    if (dt > 0) covered += Math.min(dt, ZONE_DT_CAP_S);
  }
  return Math.min(covered / dur, 1.0);
}

/** Timer -> elapsed -> declared -> record span (derivable truth only). */
function sessionDurationS(session: Session): number | null {
  const der = session.derived;
  const dec = session.declared;
  for (const v of [
    der.timerTimeS,
    der.elapsedTimeS,
    dec ? dec.timerTimeS : null,
    dec ? dec.elapsedTimeS : null,
  ]) {
    if (v) return v; // Python truthiness: 0.0 falls through
  }
  const times = session.records.time.filter((t): t is number => t !== null);
  if (times.length >= 2) {
    const span = (times[times.length - 1] as number) - (times[0] as number);
    return span > 0 ? span : null;
  }
  return null;
}

/**
 * Estimator ladder: power+ftp -> hr TRIMP -> null. A missing number beats an
 * invented one; the report records the omission reason.
 */
export function workoutLoad(
  session: Session,
  settings: AthleteSettings | null,
): LoadEstimate | null {
  const rec = session.records;
  if (settings?.ftpW) {
    const pw = getStream(rec, "power");
    if (pw !== undefined) {
      const wap = weightedAvgPower(pw.values);
      const dur = sessionDurationS(session);
      if (wap !== null && dur) {
        const ir = intensityRatio(wap, settings.ftpW);
        return {
          value: loadScore(dur, ir),
          basis: "power+ftp",
          components: { weighted_avg_power: wap, intensity_ratio: ir, duration_s: dur },
        };
      }
    }
  }
  if (settings?.maxHr && settings?.restingHr) {
    const hr = getStream(rec, "heart_rate");
    const cov = hrCoverageFraction(session);
    if (hr !== undefined && cov !== null && cov >= TRIMP_MIN_COVERAGE) {
      const t = trimp(rec.time, hr.values, {
        restingHr: settings.restingHr,
        maxHr: settings.maxHr,
        sex: settings.sex ?? null,
      });
      if (t !== null) {
        const basis = settings.sex ? "hr-trimp" : "hr-trimp (male-coefficient default)";
        return {
          value: t,
          basis,
          components: { max_hr: settings.maxHr, resting_hr: settings.restingHr },
        };
      }
    }
  }
  return null;
}

/** One day in the fitness/fatigue/form series. Days are "YYYY-MM-DD" strings. */
export interface FitnessPoint {
  readonly day: string;
  readonly load: number;
  readonly fitness: number;
  readonly fatigue: number;
  readonly form: number;
}

/**
 * Impulse-response over a day series. Missing days count as 0 load. Seeds at 0.
 *
 * Days are ISO "YYYY-MM-DD" strings (Python uses `date`); day arithmetic goes
 * through the same civil-date math the timestamp formatter uses, so `Date` stays
 * banned.
 */
export function fitnessFatigueForm(dailyLoads: readonly [string, number][]): FitnessPoint[] {
  if (dailyLoads.length === 0) return [];
  const byDay = new Map<string, number>();
  for (const [d, v] of dailyLoads) byDay.set(d, (byDay.get(d) ?? 0) + v);
  const days = [...byDay.keys()].sort();
  const first = days[0] as string;
  const last = days[days.length - 1] as string;
  const kFit = 1.0 - Math.exp(-1.0 / FITNESS_TC_DAYS);
  const kFat = 1.0 - Math.exp(-1.0 / FATIGUE_TC_DAYS);
  let fitness = 0;
  let fatigue = 0;
  const out: FitnessPoint[] = [];
  for (let day = first; day <= last; day = nextDay(day)) {
    const prevFitness = fitness;
    const prevFatigue = fatigue;
    const load = byDay.get(day) ?? 0;
    fitness += (load - fitness) * kFit;
    fatigue += (load - fatigue) * kFat;
    out.push({ day, load, fitness, fatigue, form: prevFitness - prevFatigue });
  }
  return out;
}

const DAYS_IN_MONTH = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

function isLeap(y: number): boolean {
  return (y % 4 === 0 && y % 100 !== 0) || y % 400 === 0;
}

function nextDay(day: string): string {
  const [y, m, d] = day.split("-").map(Number) as [number, number, number];
  const dim = m === 2 && isLeap(y) ? 29 : (DAYS_IN_MONTH[m - 1] as number);
  let ny = y;
  let nm = m;
  let nd = d + 1;
  if (nd > dim) {
    nd = 1;
    nm += 1;
    if (nm > 12) {
      nm = 1;
      ny += 1;
    }
  }
  return `${String(ny).padStart(4, "0")}-${String(nm).padStart(2, "0")}-${String(nd).padStart(2, "0")}`;
}
