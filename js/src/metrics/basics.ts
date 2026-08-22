/**
 * Optional analytics on chiptime's honest streams.
 *
 * Twin of `python/src/chiptime/metrics/_basics.py`. Everything inherits the
 * streams' guarantees: sentinels are already null, zero is real (taxonomy #64), so
 * a 65535 W spike can never corrupt a curve. Missing data shrinks coverage; it is
 * never filled in.
 */

import type { Session } from "../model.js";
import { pyRound, pySum } from "../numeric.js";

export const MEAN_MAX_MIN_COVERAGE = 0.9; // a window needs >=90% present samples
export const ZONE_DT_CAP_S = 30.0; // ADR-0005 gap policy reused

/**
 * Best rolling average per window size, in the RECORD domain.
 *
 * Windows with less than 90% data coverage return null — absence is not zero.
 */
export function meanMax(
  values: readonly unknown[],
  windows: readonly number[],
): Map<number, number | null> {
  const nums: (number | null)[] = values.map((v) => (typeof v === "number" ? v : null));
  const n = nums.length;
  const prefix: number[] = [0];
  const present: number[] = [0];
  for (const v of nums) {
    prefix.push((prefix[prefix.length - 1] as number) + (v ?? 0));
    present.push((present[present.length - 1] as number) + (v !== null ? 1 : 0));
  }
  const out = new Map<number, number | null>();
  for (const w of windows) {
    if (w <= 0 || w > n) {
      out.set(w, null);
      continue;
    }
    let best: number | null = null;
    const minPresent = Math.trunc(w * MEAN_MAX_MIN_COVERAGE + 0.999999);
    for (let i = 0; i <= n - w; i++) {
      const have = (present[i + w] as number) - (present[i] as number);
      if (have < minPresent) continue;
      const avg = ((prefix[i + w] as number) - (prefix[i] as number)) / have;
      if (best === null || avg > best) best = avg;
    }
    out.set(w, best);
  }
  return out;
}

/**
 * Seconds spent per zone. Zones: (-inf, b0], (b0, b1], ..., (bn, inf) —
 * bounds.length+1 buckets. dt attribution per record, capped at 30 s (a gap is a
 * gap, not an hour in zone 2). Null samples contribute nowhere.
 */
export function timeInZones(
  times: readonly (number | null)[],
  values: readonly unknown[],
  bounds: readonly number[],
): number[] {
  const zones = new Array<number>(bounds.length + 1).fill(0);
  for (let i = 0; i < times.length - 1; i++) {
    const t0 = times[i];
    const t1 = times[i + 1];
    const v = values[i];
    if (t0 === null || t0 === undefined || t1 === null || t1 === undefined) continue;
    if (typeof v !== "number") continue;
    let dt = t1 - t0;
    if (dt <= 0) continue;
    dt = Math.min(dt, ZONE_DT_CAP_S);
    let z = 0;
    for (const b of bounds) {
      if (v > b) z += 1;
      else break;
    }
    zones[z] = (zones[z] as number) + dt;
  }
  return zones;
}

/**
 * Per-active-length SWOLF (strokes + seconds) and the mean over lengths where both
 * parts are present. Pool swimming only (#73).
 */
export function swolf(session: Session): [(number | null)[], number | null] {
  const per: (number | null)[] = [];
  for (const ln of session.lengths) {
    if (ln.lengthType !== "active") continue;
    if (ln.totalStrokes === null || ln.totalElapsedTimeS === null) {
      per.push(null);
      continue;
    }
    per.push(pyRound(ln.totalStrokes + ln.totalElapsedTimeS));
  }
  const known = per.filter((v): v is number => v !== null);
  return [per, known.length > 0 ? pySum(known) / known.length : null];
}
