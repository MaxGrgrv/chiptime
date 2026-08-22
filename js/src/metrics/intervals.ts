/**
 * Interval & structure detection — evidence ladder, deterministic bands.
 *
 * Twin of `python/src/chiptime/metrics/intervals.py`. Structure is a *reading* of
 * the data: every result carries its evidence basis, and "no clear structure" is a
 * first-class answer (ADR-0008 §5/§6). Ladder: structured-workout steps → manual
 * laps → swim sets → band detection on the primary signal → none.
 */

import type { Message } from "../message.js";
import { type Session, getStream } from "../model.js";
import { pyFixed, pyMedian, pyPstdev, pySum } from "../numeric.js";
import { formatPace, paceSeconds } from "./pacing.js";
import type { AthleteSettings } from "./settings.js";
import { type PaceStyle, primarySignal, profileFor } from "./sports.js";

// --- detection constants (copied verbatim from the Python) ----------------
export const SMOOTH_WINDOW = 11;
export const REF_LOW_Q = 0.2;
export const REF_HIGH_Q = 0.8;
export const WORK_BAND = 1.1;
export const RECOVERY_BAND = 0.85;
export const MIN_WORK_S = 20.0;
export const MIN_RECOVERY_S = 15.0;
export const MIN_WORK_REPS = 3;
export const MAX_DURATION_CV = 0.4;
export const SWIM_SET_REST_MIN_S = 10.0;
export const REPEAT_DURATION_TOL = 0.25;
export const REPEAT_INTENSITY_TOL = 0.1;

const STEP_KIND: Readonly<Record<string, string>> = {
  active: "work",
  interval: "work",
  rest: "rest",
  recovery: "recovery",
  warmup: "warmup",
  cooldown: "cooldown",
};

/** One segment of the workout, in time order. Times are FIT seconds. */
export interface Interval {
  readonly index: number;
  readonly kind: string;
  readonly startTime: number | null;
  readonly endTime: number | null;
  readonly durationS: number | null;
  readonly distanceM: number | null;
  readonly avgPrimary: number | null;
  readonly avgHr: number | null;
  readonly lengths: number | null;
  readonly stepIndex: number | null;
}

/** N similar consecutive work intervals, in athlete notation. */
export interface RepeatGroup {
  readonly count: number;
  readonly kind: string;
  readonly meanDurationS: number | null;
  readonly meanDistanceM: number | null;
  readonly meanPrimary: number | null;
  readonly meanRestS: number | null;
  readonly label: string;
  readonly firstIndex: number;
}

/** The structure reading for one session — always with its evidence. */
export interface IntervalStructure {
  readonly basis: string;
  readonly intervals: readonly Interval[];
  readonly repeats: readonly RepeatGroup[];
  readonly note: string | null;
}

function structure(
  basis: string,
  intervals: Interval[] = [],
  repeats: RepeatGroup[] = [],
  note: string | null = null,
): IntervalStructure {
  return { basis, intervals, repeats, note };
}

// --- helpers --------------------------------------------------------------

function num(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

function get(m: Message, name: string): unknown {
  return m.fields.get(name)?.value ?? null;
}

/** (tRelS, fitTime, value) for records where time+value are present. */
function series(session: Session, name: string): [number, number, number][] {
  const s = getStream(session.records, name);
  if (s === undefined) return [];
  const out: [number, number, number][] = [];
  let t0: number | null = null;
  for (let i = 0; i < session.records.time.length; i++) {
    const t = session.records.time[i];
    const v = num(s.values[i]);
    if (t === null || t === undefined || v === null) continue;
    if (t0 === null) t0 = t;
    out.push([t - t0, t, v]);
  }
  return out;
}

/** (avgPrimary, avgHr, distanceM) over [start, end) from streams. */
function aggregate(
  session: Session,
  start: number,
  end: number,
  primaryStream: string | null,
): [number | null, number | null, number | null] {
  const rec = session.records;
  const hr = getStream(rec, "heart_rate");
  const prim = primaryStream ? getStream(rec, primaryStream) : undefined;
  const dist = getStream(rec, "distance");
  let pSum = 0;
  let pN = 0;
  let hSum = 0;
  let hN = 0;
  let dFirst: number | null = null;
  let dLast: number | null = null;
  for (let i = 0; i < rec.time.length; i++) {
    const t = rec.time[i];
    if (t === null || t === undefined || t < start || t >= end) continue;
    if (prim !== undefined) {
      const v = num(prim.values[i]);
      if (v !== null) {
        pSum += v;
        pN += 1;
      }
    }
    if (hr !== undefined) {
      const v = num(hr.values[i]);
      if (v !== null) {
        hSum += v;
        hN += 1;
      }
    }
    if (dist !== undefined) {
      const v = num(dist.values[i]);
      if (v !== null) {
        if (dFirst === null) dFirst = v;
        dLast = v;
      }
    }
  }
  return [
    pN ? pSum / pN : null,
    hN ? hSum / hN : null,
    dFirst !== null && dLast !== null ? dLast - dFirst : null,
  ];
}

function rollingMedian(vals: number[], window: number): number[] {
  const half = Math.floor(window / 2);
  const n = vals.length;
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    out.push(pyMedian(vals.slice(Math.max(0, i - half), Math.min(n, i + half + 1))));
  }
  return out;
}

function lapMessages(messages: readonly Message[] | null): Message[] {
  return (messages ?? []).filter((m) => m.name === "lap");
}

/**
 * Midpoint of the low/high quantiles of positive samples — a reference that sits
 * *between* work and recovery levels, so both bands can fire regardless of which
 * level dominates the file.
 */
function bandReference(values: readonly number[]): number {
  const pos = values.filter((v) => v > 0).sort((a, b) => a - b);
  if (pos.length === 0) return 0;
  const lo = pos[Math.trunc(REF_LOW_Q * (pos.length - 1))] as number;
  const hi = pos[Math.trunc(REF_HIGH_Q * (pos.length - 1))] as number;
  return (lo + hi) / 2;
}

function classifyRelative(avg: number | null, ref: number): string {
  if (avg === null || ref <= 0) return "steady";
  if (avg >= WORK_BAND * ref) return "work";
  if (avg <= RECOVERY_BAND * ref) return "recovery";
  return "steady";
}

// --- ladder rungs ---------------------------------------------------------

function fromLaps(
  session: Session,
  messages: readonly Message[],
  primaryStream: string | null,
): IntervalStructure | null {
  const laps = lapMessages(messages);
  if (laps.length === 0) return null;
  const stepIntensity = new Map<number, string>();
  for (const m of messages) {
    if (m.name === "workout_step") {
      const idx = get(m, "message_index");
      const intensity = get(m, "intensity");
      if (typeof idx === "number" && Number.isInteger(idx) && typeof intensity === "string") {
        stepIntensity.set(idx, intensity);
      }
    }
  }
  const stepped = laps.filter((m) => {
    const v = get(m, "wkt_step_index");
    return typeof v === "number" && Number.isInteger(v);
  });
  const manual = laps.filter((m) => get(m, "lap_trigger") === "manual");
  let use: Message[];
  let basis: string;
  if (stepped.length > 0) {
    use = laps;
    basis = "steps:workout";
  } else if (manual.length >= 2) {
    // single lap → ignore laps, auto-detect (survey §12)
    use = laps;
    basis = "laps:manual";
  } else {
    return null;
  }

  // Faithful quirk: Python checks `isinstance(m.get("start_time"), datetime)`, but
  // decode yields date_time values as ISO *strings*, so the check is always False —
  // lap intervals carry None times and the stream-aggregation path never runs.
  // Averages come from the lap's declared fields. Reproduced, not "fixed".
  const perLap: [
    Message,
    number | null,
    number | null,
    number | null,
    number | null,
    number | null,
  ][] = [];
  for (const m of use) {
    const start: number | null = null;
    const end: number | null = null;
    let avgP: number | null =
      primaryStream === "power"
        ? num(get(m, "avg_power"))
        : (num(get(m, "avg_speed")) ?? num(get(m, "enhanced_avg_speed")));
    if (avgP === null) avgP = null;
    const avgHr = num(get(m, "avg_heart_rate"));
    const dist = num(get(m, "total_distance"));
    perLap.push([m, avgP, avgHr, dist, start, end]);
  }
  const ref = bandReference(perLap.map(([, v]) => v).filter((v): v is number => v !== null));

  const intervals: Interval[] = [];
  perLap.forEach(([m, avgP, avgHr, dist, start, end], i) => {
    const stepIdxV = get(m, "wkt_step_index");
    const stepIdx = typeof stepIdxV === "number" && Number.isInteger(stepIdxV) ? stepIdxV : null;
    let kind: string;
    if (basis === "steps:workout" && stepIdx !== null) {
      kind = STEP_KIND[stepIntensity.get(stepIdx) ?? ""] ?? "steady";
    } else {
      kind = classifyRelative(avgP, ref);
    }
    // Python: total_timer_time or total_elapsed_time — `or` semantics.
    const dur = num(get(m, "total_timer_time")) || num(get(m, "total_elapsed_time"));
    intervals.push({
      index: i + 1,
      kind,
      startTime: start,
      endTime: end,
      durationS: dur,
      distanceM: dist,
      avgPrimary: avgP,
      avgHr,
      lengths: null,
      stepIndex: stepIdx,
    });
  });
  return structure(basis, intervals, groupRepeats(intervals, session));
}

function swimSets(session: Session, messages: readonly Message[] | null): IntervalStructure | null {
  const active = session.lengths.filter((ln) => (ln.lengthType ?? "active") === "active");
  if (active.length === 0) return null;
  let poolLen: number | null = null;
  for (const m of messages ?? []) {
    if (m.name === "session") {
      poolLen = num(get(m, "pool_length"));
      if (poolLen) break;
    }
  }
  if (!poolLen) {
    const d = session.derived.distanceM || (session.declared ? session.declared.distanceM : null);
    poolLen = d && active.length > 0 ? d / active.length : null;
  }

  // group active lengths: wall rest below SWIM_SET_REST_MIN_S joins a swim
  const groups: number[][] = [[0]];
  for (let i = 1; i < active.length; i++) {
    const prevEnd = (active[i - 1] as { endTime: number | null }).endTime;
    const curStart = (active[i] as { startTime: number | null }).startTime;
    const rest = prevEnd !== null && curStart !== null ? curStart - prevEnd : null;
    if (rest !== null && rest < SWIM_SET_REST_MIN_S) {
      (groups[groups.length - 1] as number[]).push(i);
    } else {
      groups.push([i]);
    }
  }
  const intervals: Interval[] = [];
  groups.forEach((idxs, gi) => {
    const lens = idxs.map((i) => active[i] as (typeof active)[number]);
    // Python: sum(...) or None — a zero sum falls through to the time-span fallback.
    let dur: number | null = pySum(lens.map((ln) => ln.totalElapsedTimeS ?? 0)) || null;
    const first = lens[0] as (typeof active)[number];
    const last = lens[lens.length - 1] as (typeof active)[number];
    if (dur === null && first.startTime !== null && last.endTime !== null) {
      dur = last.endTime - first.startTime;
    }
    const dist = poolLen ? poolLen * lens.length : null;
    const speed = dist && dur ? dist / dur : null;
    intervals.push({
      index: gi + 1,
      kind: "work",
      startTime: first.startTime,
      endTime: last.endTime,
      durationS: dur,
      distanceM: dist,
      avgPrimary: speed,
      avgHr: null,
      lengths: lens.length,
      stepIndex: null,
    });
  });
  return structure("lengths:sets", intervals, groupRepeats(intervals, session));
}

function detect(session: Session, primaryKind: string, primaryStream: string): IntervalStructure {
  const ser = series(session, primaryStream);
  if (ser.length < SMOOTH_WINDOW) {
    return structure("none", [], [], "too little data to detect structure");
  }
  const smoothed = rollingMedian(
    ser.map(([, , v]) => v),
    SMOOTH_WINDOW,
  );
  const ref = bandReference(smoothed);
  if (ref <= 0) return structure("none");

  // hysteresis state machine → runs of (state, firstI, lastI)
  const runs: [string, number, number][] = [];
  let state = "recovery";
  smoothed.forEach((v, i) => {
    let next: string;
    if (v >= WORK_BAND * ref) next = "work";
    else if (v <= RECOVERY_BAND * ref) next = "recovery";
    else next = state; // hysteresis: between bands keeps the current state
    const lastRun = runs[runs.length - 1];
    if (lastRun !== undefined && lastRun[0] === next) {
      lastRun[2] = i;
    } else {
      runs.push([next, i, i]);
    }
    state = next;
  });

  const durOf = (r: [string, number, number]): number =>
    (ser[r[2]] as [number, number, number])[0] - (ser[r[1]] as [number, number, number])[0];

  // merge runs shorter than their minimum into the previous run (spike guard)
  const merged: [string, number, number][] = [];
  for (const r of runs) {
    const minS = r[0] === "work" ? MIN_WORK_S : MIN_RECOVERY_S;
    const last = merged[merged.length - 1];
    if (last !== undefined && (durOf(r) < minS || last[0] === r[0])) {
      last[2] = r[2];
    } else if (merged.length === 0 && durOf(r) < minS) {
      merged.push(["recovery", r[1], r[2]]); // leading stub is warm-in
    } else {
      merged.push([r[0], r[1], r[2]]);
    }
  }

  const workRuns = merged.filter((r) => r[0] === "work");
  if (workRuns.length < MIN_WORK_REPS) {
    return structure(
      "none",
      [],
      [],
      `${workRuns.length} work efforts found; need >= ${MIN_WORK_REPS} similar reps to call it structure`,
    );
  }
  const durs = workRuns.map(durOf);
  const meanD = pySum(durs) / durs.length;
  const cv = meanD > 0 ? pyPstdev(durs) / meanD : 1.0;
  if (cv > MAX_DURATION_CV) {
    // Python's f"{cv:.0%}": value*100 formatted .0f (half-even) plus '%'.
    return structure(
      "none",
      [],
      [],
      `work-effort durations too varied (CV ${pyFixed(cv * 100, 0)}%) to call it interval structure`,
    );
  }

  const intervals: Interval[] = [];
  merged.forEach((r, i) => {
    const sStart = ser[r[1]] as [number, number, number];
    const sEnd = ser[r[2]] as [number, number, number];
    const [avgP, avgHr, dist] = aggregate(session, sStart[1], sEnd[1], primaryStream);
    intervals.push({
      index: i + 1,
      kind: r[0],
      startTime: sStart[1],
      endTime: sEnd[1],
      durationS: sEnd[0] - sStart[0],
      distanceM: dist,
      avgPrimary: avgP,
      avgHr,
      lengths: null,
      stepIndex: null,
    });
  });
  const basis = primaryKind === "power" ? "detected:power-steps" : "detected:speed-steps";
  return structure(basis, intervals, groupRepeats(intervals, session));
}

// --- repeat grouping ------------------------------------------------------

/** Consecutive similar work intervals → "N x ..." groups (>= 2 reps). */
function groupRepeats(intervals: readonly Interval[], session: Session): RepeatGroup[] {
  const style = profileFor(session).paceStyle;
  const groups: Interval[][] = [];
  const rests = new Map<number, number>();
  let prevWork: Interval | null = null;
  for (const iv of intervals) {
    if (iv.kind !== "work") {
      if (
        prevWork !== null &&
        (iv.kind === "recovery" || iv.kind === "rest") &&
        iv.durationS !== null
      ) {
        rests.set(prevWork.index, iv.durationS);
      }
      continue;
    }
    const lastGroup = groups[groups.length - 1];
    if (lastGroup !== undefined && similar(lastGroup[0] as Interval, iv)) {
      lastGroup.push(iv);
    } else {
      groups.push([iv]);
    }
    prevWork = iv;
  }
  const out: RepeatGroup[] = [];
  for (const g of groups) {
    if (g.length < 2) continue;
    const durs = g.map((iv) => iv.durationS).filter((v): v is number => v !== null);
    const dists = g.map((iv) => iv.distanceM).filter((v): v is number => v !== null);
    const prims = g.map((iv) => iv.avgPrimary).filter((v): v is number => v !== null);
    const restVals = g.map((iv) => rests.get(iv.index)).filter((v): v is number => v !== undefined);
    const meanDur = durs.length ? pySum(durs) / durs.length : null;
    const meanDist = dists.length ? pySum(dists) / dists.length : null;
    const meanPrim = prims.length ? pySum(prims) / prims.length : null;
    const meanRest = restVals.length ? pySum(restVals) / restVals.length : null;
    const first = g[0] as Interval;
    out.push({
      count: g.length,
      kind: "work",
      meanDurationS: meanDur,
      meanDistanceM: meanDist,
      meanPrimary: meanPrim,
      meanRestS: meanRest,
      label: label(g.length, meanDur, meanDist, meanPrim, meanRest, style, first.lengths !== null),
      firstIndex: first.index,
    });
  }
  return out;
}

function similar(a: Interval, b: Interval): boolean {
  if (a.lengths !== null && b.lengths !== null) return a.lengths === b.lengths; // swim: same rep distance
  if (a.durationS === null || b.durationS === null) return false;
  const base = Math.max(a.durationS, b.durationS);
  if (base <= 0 || Math.abs(a.durationS - b.durationS) / base > REPEAT_DURATION_TOL) return false;
  if (a.avgPrimary !== null && b.avgPrimary !== null) {
    const pbase = Math.max(a.avgPrimary, b.avgPrimary);
    if (pbase > 0 && Math.abs(a.avgPrimary - b.avgPrimary) / pbase > REPEAT_INTENSITY_TOL) {
      return false;
    }
  }
  return true;
}

function fmtMmss(seconds: number): string {
  const total = Math.trunc(seconds + 0.5);
  const m = Math.floor(total / 60);
  const s = total - m * 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function label(
  count: number,
  dur: number | null,
  dist: number | null,
  prim: number | null,
  rest: number | null,
  style: PaceStyle,
  swim: boolean,
): string {
  let head: string;
  if (swim && dist !== null) {
    head = `${count} x ${pyFixed(dist, 0)}m`;
  } else if (dist !== null && dist >= 200 && style !== "speed") {
    head =
      dist >= 950 ? `${count} x ${pyFixed(dist / 1000, 1)}km` : `${count} x ${pyFixed(dist, 0)}m`;
  } else if (dur !== null) {
    head = `${count} x ${fmtMmss(dur)}`;
  } else {
    head = `${count} x ?`;
  }
  let at = "";
  if (prim !== null) {
    if (style === "speed") {
      at = ` @ ${pyFixed(prim, 0)} W`;
    } else {
      const pace = formatPace(paceSeconds(prim, style), style, { suffix: true });
      at = pace ? ` @ ${pace}` : "";
    }
  }
  const tail = rest !== null ? ` rest ${fmtMmss(rest)}` : "";
  return head + at + tail;
}

// --- entry point ----------------------------------------------------------

/**
 * Evidence ladder: workout steps → manual laps → swim sets → band detection →
 * none. `messages` (from ParseResult.messages) unlocks the lap and workout-step
 * rungs and pool length; without it those rungs are skipped.
 */
export function detectStructure(
  session: Session,
  messages: readonly Message[] | null = null,
  _settings: AthleteSettings | null = null,
): IntervalStructure {
  const profile = profileFor(session);
  const [kind, stream] = primarySignal(session);
  if (messages && messages.length > 0) {
    const byLaps = fromLaps(session, messages, stream);
    if (byLaps !== null) return byLaps;
  }
  if (profile.distanceFromLengths) {
    const byLengths = swimSets(session, messages);
    if (byLengths !== null) return byLengths;
  }
  if (kind === "none" || stream === null) {
    return structure("none", [], [], "no intensity stream to detect from");
  }
  return detect(session, kind, stream);
}
