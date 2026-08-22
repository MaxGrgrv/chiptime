/**
 * Pace math done right: internal SI (m/s, s), pace strictly as presentation.
 *
 * Twin of `python/src/chiptime/metrics/pacing.py`. The inverse-metric trap: pace is
 * 1/speed, so paces are never averaged — aggregate distance/time first, convert
 * last. Pace at standstill is undefined and returns null, never a huge number.
 */

import { type Session, type Totals, getStream } from "../model.js";
import { pyFixed } from "../numeric.js";
import type { PaceStyle } from "./sports.js";

const METERS: Readonly<Record<string, number>> = {
  per_km: 1000.0,
  per_100m: 100.0,
  per_500m: 500.0,
};
export const PACE_SUFFIX: Readonly<Record<string, string>> = {
  per_km: "/km",
  per_100m: "/100m",
  per_500m: "/500m",
};

/** Concept2's published erg relation: W = 2.80 / pace^3, pace in seconds/meter. */
export const CONCEPT2_COEFF = 2.8;

/** Seconds per style unit; null for absent/zero speed or style "speed". */
export function paceSeconds(speedMps: number | null, style: PaceStyle): number | null {
  if (style === "speed" || speedMps === null || speedMps <= 0.0) return null;
  return (METERS[style] as number) / speedMps;
}

export function speedFromPace(paceS: number, style: PaceStyle): number {
  if (style === "speed" || paceS <= 0.0) {
    throw new RangeError(`no distance base for style '${style}' / pace ${paceS}`);
  }
  return (METERS[style] as number) / paceS;
}

/**
 * "4:20" (/km, /100m) or "1:52.5" (/500m, rowing shows tenths).
 *
 * Rounding is explicit half-up (`int(x + 0.5)` in the Python), so banker's
 * rounding can never make two runtimes disagree on a boundary value.
 */
export function formatPace(
  paceS: number | null,
  style: PaceStyle,
  options: { suffix?: boolean } = {},
): string | null {
  if (paceS === null) return null;
  if (style === "speed") {
    throw new RangeError("style 'speed' has no pace representation; use formatSpeedKmh");
  }
  let out: string;
  if (style === "per_500m") {
    const tenths = Math.trunc(paceS * 10 + 0.5);
    const minutes = Math.floor(tenths / 600);
    const rem = tenths - minutes * 600;
    const secs = Math.floor(rem / 10);
    const tenth = rem - secs * 10;
    out = `${minutes}:${String(secs).padStart(2, "0")}.${tenth}`;
  } else {
    const total = Math.trunc(paceS + 0.5);
    const minutes = Math.floor(total / 60);
    const secs = total - minutes * 60;
    out = `${minutes}:${String(secs).padStart(2, "0")}`;
  }
  return options.suffix ? out + (PACE_SUFFIX[style] as string) : out;
}

export function formatSpeedKmh(
  speedMps: number | null,
  options: { suffix?: boolean } = {},
): string | null {
  if (speedMps === null) return null;
  const out = pyFixed(speedMps * 3.6, 1);
  return options.suffix ? `${out} km/h` : out;
}

/** Concept2 published relation (see CONCEPT2_COEFF). */
export function split500mToWatts(splitS: number): number {
  const paceSPerM = splitS / 500.0;
  return CONCEPT2_COEFF / (paceSPerM * paceSPerM * paceSPerM);
}

export function wattsToSplit500m(watts: number): number {
  return 500.0 * (CONCEPT2_COEFF / watts) ** (1.0 / 3.0);
}

/** One distance split. Absent streams give null fields, never zeros. */
export interface Split {
  readonly index: number;
  readonly startM: number;
  readonly endM: number;
  readonly durationS: number;
  readonly avgSpeedMps: number | null;
  readonly paceS: number | null;
  readonly avgHr: number | null;
  readonly avgPower: number | null;
  readonly ascentM: number | null;
  readonly descentM: number | null;
  readonly partial: boolean;
}

function num(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

/**
 * Distance-domain splits from the cumulative distance stream.
 *
 * Boundary crossings are linearly interpolated between records; each record's
 * samples are attributed to the split where its step started. No distance stream →
 * [] (pool swims split by lengths instead).
 */
export function distanceSplits(
  session: Session,
  splitM = 1000.0,
  options: { style?: PaceStyle } = {},
): Split[] {
  const style = options.style ?? "per_km";
  const rec = session.records;
  const dist = getStream(rec, "distance");
  if (dist === undefined || rec.time.length === 0 || splitM <= 0) return [];
  const hrS = getStream(rec, "heart_rate");
  const pwS = getStream(rec, "power");
  const altStream = getStream(rec, "enhanced_altitude") ?? getStream(rec, "altitude");

  const pts: [number, number, number][] = []; // (tRelS, distanceM, recordIdx)
  let t0: number | null = null;
  for (let i = 0; i < rec.time.length; i++) {
    const t = rec.time[i];
    const d = num(dist.values[i]);
    if (t === null || t === undefined || d === null) continue;
    if (t0 === null) t0 = t;
    pts.push([t - t0, d, i]);
  }
  if (pts.length < 2) return [];

  const splits: Split[] = [];
  let hrSum = 0;
  let hrN = 0;
  let pwSum = 0;
  let pwN = 0;
  let asc = 0;
  let desc = 0;
  let altSeen = false;
  let prevAlt: number | null = null;

  const sample = (idx: number): void => {
    if (hrS !== undefined) {
      const v = num(hrS.values[idx]);
      if (v !== null) {
        hrSum += v;
        hrN += 1;
      }
    }
    if (pwS !== undefined) {
      const v = num(pwS.values[idx]);
      if (v !== null) {
        pwSum += v;
        pwN += 1;
      }
    }
    if (altStream !== undefined) {
      const v = num(altStream.values[idx]);
      if (v !== null) {
        if (prevAlt !== null) {
          const delta = v - prevAlt;
          if (delta > 0) asc += delta;
          else desc += -delta;
        }
        prevAlt = v;
        altSeen = true;
      }
    }
  };

  const emit = (
    startT: number,
    endT: number,
    startD: number,
    endD: number,
    partial: boolean,
  ): void => {
    const dur = endT - startT;
    const covered = endD - startD;
    const speed = dur > 0 ? covered / dur : null;
    splits.push({
      index: splits.length + 1,
      startM: startD,
      endM: endD,
      durationS: dur,
      avgSpeedMps: speed,
      paceS: paceSeconds(speed, style),
      avgHr: hrN ? hrSum / hrN : null,
      avgPower: pwN ? pwSum / pwN : null,
      ascentM: altSeen ? asc : null,
      descentM: altSeen ? desc : null,
      partial,
    });
    hrSum = pwSum = asc = desc = 0;
    hrN = pwN = 0;
    altSeen = false;
  };

  let [startT, startD] = pts[0] as [number, number, number];
  const firstIdx = (pts[0] as [number, number, number])[2];
  let boundary = startD + splitM;
  sample(firstIdx);
  let prevT = startT;
  let prevD = startD;
  for (let k = 1; k < pts.length; k++) {
    const [curT, curD, curI] = pts[k] as [number, number, number];
    while (curD >= boundary && curD > prevD) {
      const frac = (boundary - prevD) / (curD - prevD);
      const tCross = prevT + frac * (curT - prevT);
      emit(startT, tCross, startD, boundary, false);
      startT = tCross;
      startD = boundary;
      boundary += splitM;
    }
    sample(curI);
    prevT = curT;
    prevD = curD;
  }
  if (prevD - startD > 0.5) emit(startT, prevT, startD, prevD, true); // trailing partial

  return splits;
}

/**
 * Overall pace from totals, preferring the moving denominator, falling back
 * timer → elapsed. Returns [paceS, basis] or null.
 */
export function sessionPaceS(session: Session, style: PaceStyle): [number, string] | null {
  let dist: number | null = null;
  for (const t of [session.derived, session.declared]) {
    if (t !== null && t.distanceM !== null && t.distanceM > 0) {
      dist = t.distanceM;
      break;
    }
  }
  if (dist === null) return null;
  const attrs: [keyof Totals, string][] = [
    ["movingTimeS", "moving"],
    ["timerTimeS", "timer"],
    ["elapsedTimeS", "elapsed"],
  ];
  for (const [attr, basis] of attrs) {
    for (const t of [session.derived, session.declared]) {
      if (t === null) continue;
      const dur = t[attr] as number | null;
      if (dur !== null && dur > 0) {
        const pace = paceSeconds(dist / dur, style);
        if (pace !== null) return [pace, basis];
      }
    }
  }
  return null;
}
