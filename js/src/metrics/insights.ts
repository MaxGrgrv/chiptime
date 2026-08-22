/**
 * Single-workout report + machine-readable insights.
 *
 * Twin of `python/src/chiptime/metrics/insights.py`. Insights follow the error-code
 * philosophy (contract #5): a stable CODE for agents, a human sentence, and numeric
 * evidence. Analyses that need absent inputs land in `omissions` with a reason.
 */

import { fitTsToIso } from "../decode.js";
import type { Message } from "../message.js";
import { type Session, getStream } from "../model.js";
import { pyFixed, pyRound, pyRoundN, pySum } from "../numeric.js";
import { meanMax, swolf, timeInZones } from "./basics.js";
import { type IntervalStructure, detectStructure } from "./intervals.js";
import {
  type LoadEstimate,
  TRIMP_MIN_COVERAGE,
  hrCoverageFraction,
  weightedAvgPower,
  workKj,
  workoutLoad,
} from "./load.js";
import { type Split, distanceSplits, formatPace, sessionPaceS } from "./pacing.js";
import type { AthleteSettings } from "./settings.js";
import { cadenceDisplay, primarySignal, profileFor } from "./sports.js";
import { hrZoneBounds, powerZoneBounds } from "./zones.js";

// --- insight thresholds (copied verbatim) ---------------------------------
export const SPLIT_DELTA_PCT = 2.0;
export const HR_DRIFT_PCT = 5.0;
export const COASTING_SHARE_PCT = 25.0;
const MIN_HALF_SAMPLES = 60;
const POWER_CURVE_WINDOWS = [5, 60, 300, 1200];

export const INSIGHT_CODES: Readonly<Record<string, string>> = {
  PACING_NEGATIVE_SPLIT: "Second half faster than the first by more than 2%",
  PACING_POSITIVE_SPLIT: "Second half slower than the first by more than 2%",
  HR_DRIFT_HIGH: "Speed/power per heartbeat fell >5% first half to second (aerobic decoupling)",
  COASTING_HIGH: "More than 25% of ride samples at 0 W",
  WORKOUT_STRUCTURE: "Repeated interval structure found (label in evidence)",
};

export interface Insight {
  readonly code: string;
  readonly message: string;
  readonly evidence: Readonly<Record<string, unknown>>;
}

/** Null-honest; `omissions` says what was not computed and why. */
export interface WorkoutReport {
  sport: string;
  subSport: string | null;
  profile: string;
  primarySignal: string;
  durationS: Map<string, number | null>;
  distanceM: number | null;
  pace: Record<string, unknown> | null;
  avgSpeedKmh: number | null;
  avgSpeedBasis: string | null;
  avgPrimary: number | null;
  maxPrimary: number | null;
  avgHr: number | null;
  maxHr: number | null;
  cadence: Record<string, unknown> | null;
  weightedAvgPower: number | null;
  variabilityRatio: number | null;
  workKj: number | null;
  powerCurve: Map<number, number | null> | null;
  swolf: number | null;
  splits: Split[];
  structure: IntervalStructure | null;
  hrZones: Record<string, unknown> | null;
  powerZones: Record<string, unknown> | null;
  load: LoadEstimate | null;
  insights: Insight[];
  omissions: string[];
}

export interface ActivityReport {
  sessions: WorkoutReport[];
}

// --- half comparisons -----------------------------------------------------

function halves(session: Session, streamName: string): [number[], number[]] {
  const s = getStream(session.records, streamName);
  if (s === undefined) return [[], []];
  const vals = s.values.filter((v): v is number => typeof v === "number");
  const mid = Math.floor(vals.length / 2);
  return [vals.slice(0, mid), vals.slice(mid)];
}

function pacingInsight(session: Session, stream: string | null): Insight | null {
  if (stream === null) return null;
  const [first, second] = halves(session, stream);
  if (first.length < MIN_HALF_SAMPLES || second.length < MIN_HALF_SAMPLES) return null;
  const a = pySum(first) / first.length;
  const b = pySum(second) / second.length;
  if (a <= 0) return null;
  const deltaPct = ((b - a) / a) * 100.0;
  const ev = {
    first_half_avg: pyRoundN(a, 3),
    second_half_avg: pyRoundN(b, 3),
    delta_pct: pyRoundN(deltaPct, 1),
    stream,
  };
  if (deltaPct >= SPLIT_DELTA_PCT) {
    return {
      code: "PACING_NEGATIVE_SPLIT",
      message: `Second half ${pyFixed(deltaPct, 1)}% faster than the first.`,
      evidence: ev,
    };
  }
  if (deltaPct <= -SPLIT_DELTA_PCT) {
    return {
      code: "PACING_POSITIVE_SPLIT",
      message: `Second half ${pyFixed(Math.abs(deltaPct), 1)}% slower than the first.`,
      evidence: ev,
    };
  }
  return null;
}

function hrDriftInsight(session: Session, stream: string | null): Insight | null {
  if (stream === null) return null;
  const eff = getStream(session.records, stream);
  const hr = getStream(session.records, "heart_rate");
  if (eff === undefined || hr === undefined) return null;
  const pairs: [number, number][] = [];
  for (let i = 0; i < eff.values.length; i++) {
    const e = eff.values[i];
    const h = hr.values[i];
    if (typeof e === "number" && typeof h === "number" && h > 0) pairs.push([e, h]);
  }
  const mid = Math.floor(pairs.length / 2);
  if (mid < MIN_HALF_SAMPLES) return null;

  const ef = (chunk: [number, number][]): number => {
    const se = pySum(chunk.map(([e]) => e));
    const sh = pySum(chunk.map(([, h]) => h));
    return sh > 0 ? se / sh : 0;
  };

  const ef1 = ef(pairs.slice(0, mid));
  const ef2 = ef(pairs.slice(mid));
  if (ef1 <= 0) return null;
  const driftPct = ((ef1 - ef2) / ef1) * 100.0;
  if (driftPct <= HR_DRIFT_PCT) return null;
  return {
    code: "HR_DRIFT_HIGH",
    message: `Output per heartbeat fell ${pyFixed(driftPct, 1)}% from first half to second — aerobic drift.`,
    evidence: {
      drift_pct: pyRoundN(driftPct, 1),
      stream,
      first_half_ef: pyRoundN(ef1, 4),
      second_half_ef: pyRoundN(ef2, 4),
    },
  };
}

function coastingInsight(session: Session): Insight | null {
  if (profileFor(session).key !== "cycling") return null;
  const pw = getStream(session.records, "power");
  if (pw === undefined) return null;
  const present = pw.values.filter((v): v is number => typeof v === "number");
  if (present.length < MIN_HALF_SAMPLES) return null;
  let zeros = 0;
  for (const v of present) if (v === 0) zeros++;
  const zeroShare = (zeros / present.length) * 100.0;
  if (zeroShare < COASTING_SHARE_PCT) return null;
  return {
    code: "COASTING_HIGH",
    message: `${pyFixed(zeroShare, 0)}% of samples at 0 W (coasting).`,
    evidence: { zero_share_pct: pyRoundN(zeroShare, 1) },
  };
}

// --- report builder -------------------------------------------------------

export function analyzeSession(
  session: Session,
  messages: readonly Message[] | null = null,
  settings: AthleteSettings | null = null,
): WorkoutReport {
  const profile = profileFor(session);
  const [kind, stream] = primarySignal(session);
  const rep: WorkoutReport = {
    sport: session.sport,
    subSport: session.subSport,
    profile: profile.key,
    primarySignal: kind,
    durationS: new Map(),
    distanceM: null,
    pace: null,
    avgSpeedKmh: null,
    avgSpeedBasis: null,
    avgPrimary: null,
    maxPrimary: null,
    avgHr: null,
    maxHr: null,
    cadence: null,
    weightedAvgPower: null,
    variabilityRatio: null,
    workKj: null,
    powerCurve: null,
    swolf: null,
    splits: [],
    structure: null,
    hrZones: null,
    powerZones: null,
    load: null,
    insights: [],
    omissions: [],
  };

  const der = session.derived;
  const dec = session.declared;
  // Python `or`: 0.0 falls through to the declared value.
  rep.durationS.set("elapsed", der.elapsedTimeS || (dec ? dec.elapsedTimeS : null));
  rep.durationS.set("timer", der.timerTimeS || (dec ? dec.timerTimeS : null));
  rep.durationS.set("moving", der.movingTimeS);
  rep.distanceM = der.distanceM || (dec ? dec.distanceM : null);

  // pace / speed presentation per profile
  const got = profile.paceStyle !== "speed" ? sessionPaceS(session, profile.paceStyle) : null;
  if (got !== null) {
    const [paceS, basis] = got;
    rep.pace = {
      seconds: pyRoundN(paceS, 1),
      style: profile.paceStyle,
      formatted: formatPace(paceS, profile.paceStyle, { suffix: true }),
      basis,
    };
  }
  if (rep.distanceM) {
    for (const key of ["moving", "timer", "elapsed"]) {
      const durForSpeed = rep.durationS.get(key);
      if (durForSpeed) {
        rep.avgSpeedKmh = pyRoundN((rep.distanceM / durForSpeed) * 3.6, 2);
        rep.avgSpeedBasis = key;
        break;
      }
    }
  }

  const streamStats = (name: string): [number | null, number | null] => {
    const s = getStream(session.records, name);
    if (s === undefined) return [null, null];
    const vals = s.values.filter((v): v is number => typeof v === "number");
    if (vals.length === 0) return [null, null];
    let mx = vals[0] as number;
    for (const v of vals) if (v > mx) mx = v;
    return [pySum(vals) / vals.length, mx];
  };

  if (stream !== null) [rep.avgPrimary, rep.maxPrimary] = streamStats(stream);
  [rep.avgHr, rep.maxHr] = streamStats("heart_rate");

  const cadAvg = streamStats("cadence")[0];
  if (cadAvg !== null) {
    const [val, units, note] = cadenceDisplay(cadAvg, profile);
    rep.cadence = { value: val !== null ? pyRoundN(val, 1) : null, units, note };
  }

  const pw = getStream(session.records, "power");
  if (pw !== undefined) {
    rep.weightedAvgPower = weightedAvgPower(pw.values);
    if (rep.weightedAvgPower !== null) rep.weightedAvgPower = pyRoundN(rep.weightedAvgPower, 1);
    if (rep.weightedAvgPower && rep.avgPrimary && kind === "power") {
      rep.variabilityRatio = pyRoundN(rep.weightedAvgPower / rep.avgPrimary, 3);
    }
    const kj = workKj(session.records.time, pw.values);
    rep.workKj = kj !== null ? pyRoundN(kj, 1) : null;
    const curve = meanMax(pw.values, POWER_CURVE_WINDOWS);
    rep.powerCurve = new Map(
      [...curve.entries()].map(([w, v]) => [w, v !== null ? pyRoundN(v, 1) : null]),
    );
  }

  if (profile.distanceFromLengths && session.lengths.length > 0) {
    rep.swolf = swolf(session)[1];
  }

  rep.splits =
    profile.paceStyle === "per_km"
      ? distanceSplits(session, 1000.0, { style: profile.paceStyle })
      : [];
  rep.structure = detectStructure(session, messages, settings);

  // zones: only from settings or the file, never estimated (ADR-0008 §4)
  const [hb, hbasis] = hrZoneBounds(settings, messages);
  const hrStream = getStream(session.records, "heart_rate");
  if (hb !== null && hrStream !== undefined) {
    rep.hrZones = {
      bounds: [...hb],
      basis: hbasis,
      seconds: timeInZones(session.records.time, hrStream.values, [...hb]),
    };
  } else if (hrStream !== undefined) {
    rep.omissions.push("hr_zones: no zone bounds in settings or file");
  }
  const [pb, pbasis] = powerZoneBounds(settings, messages);
  if (pb !== null && pw !== undefined) {
    rep.powerZones = {
      bounds: [...pb],
      basis: pbasis,
      seconds: timeInZones(session.records.time, pw.values, [...pb]),
    };
  } else if (pw !== undefined) {
    rep.omissions.push("power_zones: no zone bounds in settings or file");
  }

  rep.load = workoutLoad(session, settings);
  if (rep.load === null) {
    if (pw !== undefined && (settings === null || !settings.ftpW)) {
      rep.omissions.push("load: power present but no ftp_w in settings");
    } else if (hrStream !== undefined) {
      if (settings === null || !(settings.maxHr && settings.restingHr)) {
        rep.omissions.push("load: hr present but no max_hr+resting_hr in settings");
      } else {
        const cov = hrCoverageFraction(session);
        if (cov !== null && cov < TRIMP_MIN_COVERAGE) {
          rep.omissions.push(
            `load: hr covers only ${pyFixed(cov * 100, 0)}% of the session (< ${pyFixed(TRIMP_MIN_COVERAGE * 100, 0)}%); trimp would understate load`,
          );
        }
      }
    }
  }

  for (const maybe of [
    pacingInsight(session, stream),
    hrDriftInsight(session, stream),
    coastingInsight(session),
  ]) {
    if (maybe !== null) rep.insights.push(maybe);
  }
  if (rep.structure !== null && rep.structure.repeats.length > 0) {
    rep.insights.push({
      code: "WORKOUT_STRUCTURE",
      message: `Interval structure: ${rep.structure.repeats.map((g) => g.label).join("; ")}`,
      evidence: {
        basis: rep.structure.basis,
        labels: rep.structure.repeats.map((g) => g.label),
      },
    });
  }
  return rep;
}

/** Report per session from a ParseResult (uses `.activity` and `.messages`). */
export function analyze(
  result: { activity: unknown; messages: Message[] },
  settings: AthleteSettings | null = null,
): ActivityReport {
  const activity = result.activity as { sessions: Session[] } | null;
  const messages = result.messages;
  if (activity === null) return { sessions: [] };
  return {
    sessions: activity.sessions.map((s) => analyzeSession(s, messages, settings)),
  };
}

// --- JSON serialization (the CLI's --json path) ---------------------------

/**
 * Python-int-typed report fields. Everything else numeric is a Python float, and
 * `json.dumps` writes an integral float as `119.0` where `JSON.stringify` would
 * give `119` — so the serializer needs to know which is which by key.
 */
const INT_FIELDS = new Set(["index", "count", "first_index", "step_index", "lengths"]);

function isoPlus00(t: number | null): string | null {
  // Python's datetime.isoformat() on a tz-aware UTC value: "+00:00", not "Z", and
  // fractional times carry microseconds — datetime.fromtimestamp rounds the
  // fraction to the nearest microsecond (half-even), and isoformat prints
  // ".%06d" only when nonzero.
  if (t === null) return null;
  let whole = Math.floor(t);
  let micro = pyRound((t - whole) * 1e6);
  if (micro >= 1_000_000) {
    whole += 1;
    micro = 0;
  }
  const base = fitTsToIso(whole).slice(0, -1); // strip Z
  const frac = micro > 0 ? `.${String(micro).padStart(6, "0")}` : "";
  return `${base}${frac}+00:00`;
}

/** The `to_dict()` plain tree, snake_case keys in dataclass field order. */
export function reportToPlain(report: ActivityReport): unknown {
  return { sessions: report.sessions.map(sessionPlain) };
}

function splitPlain(s: Split): Record<string, unknown> {
  return {
    index: s.index,
    start_m: s.startM,
    end_m: s.endM,
    duration_s: s.durationS,
    avg_speed_mps: s.avgSpeedMps,
    pace_s: s.paceS,
    avg_hr: s.avgHr,
    avg_power: s.avgPower,
    ascent_m: s.ascentM,
    descent_m: s.descentM,
    partial: s.partial,
  };
}

function structurePlain(st: IntervalStructure): Record<string, unknown> {
  return {
    basis: st.basis,
    intervals: st.intervals.map((iv) => ({
      index: iv.index,
      kind: iv.kind,
      start_time: isoPlus00(iv.startTime),
      end_time: isoPlus00(iv.endTime),
      duration_s: iv.durationS,
      distance_m: iv.distanceM,
      avg_primary: iv.avgPrimary,
      avg_hr: iv.avgHr,
      lengths: iv.lengths,
      step_index: iv.stepIndex,
    })),
    repeats: st.repeats.map((g) => ({
      count: g.count,
      kind: g.kind,
      mean_duration_s: g.meanDurationS,
      mean_distance_m: g.meanDistanceM,
      mean_primary: g.meanPrimary,
      mean_rest_s: g.meanRestS,
      label: g.label,
      first_index: g.firstIndex,
    })),
    note: st.note,
  };
}

function sessionPlain(rep: WorkoutReport): Record<string, unknown> {
  return {
    sport: rep.sport,
    sub_sport: rep.subSport,
    profile: rep.profile,
    primary_signal: rep.primarySignal,
    duration_s: Object.fromEntries(rep.durationS),
    distance_m: rep.distanceM,
    pace: rep.pace,
    avg_speed_kmh: rep.avgSpeedKmh,
    avg_speed_basis: rep.avgSpeedBasis,
    avg_primary: rep.avgPrimary,
    max_primary: rep.maxPrimary,
    avg_hr: rep.avgHr,
    max_hr: rep.maxHr,
    cadence: rep.cadence,
    weighted_avg_power: rep.weightedAvgPower,
    variability_ratio: rep.variabilityRatio,
    work_kj: rep.workKj,
    power_curve:
      rep.powerCurve === null
        ? null
        : Object.fromEntries([...rep.powerCurve.entries()].map(([w, v]) => [String(w), v])),
    swolf: rep.swolf,
    splits: rep.splits.map(splitPlain),
    structure: rep.structure === null ? null : structurePlain(rep.structure),
    hr_zones: rep.hrZones,
    power_zones: rep.powerZones,
    load:
      rep.load === null
        ? null
        : { value: rep.load.value, basis: rep.load.basis, components: rep.load.components },
    insights: rep.insights.map((i) => ({
      code: i.code,
      message: i.message,
      evidence: i.evidence,
    })),
    omissions: [...rep.omissions],
  };
}

/**
 * `json.dumps(tree, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`,
 * with Python's float/int distinction recovered from the INT_FIELDS key set.
 */
export function dumpsReportJson(tree: unknown): string {
  return emit(tree, null);
}

function emit(v: unknown, key: string | null): string {
  if (v === null || v === undefined) return "null";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "string") return JSON.stringify(v);
  if (typeof v === "number") {
    if (Number.isInteger(v) && !INT_FIELDS.has(key ?? "")) {
      // A Python float serializes with its .0; report ints are the named fields.
      return `${v}.0`;
    }
    return String(v);
  }
  if (Array.isArray(v)) return `[${v.map((x) => emit(x, key)).join(",")}]`;
  const entries = Object.entries(v as Record<string, unknown>).sort(([a], [b]) =>
    a < b ? -1 : a > b ? 1 : 0,
  );
  return `{${entries.map(([k, val]) => `${JSON.stringify(k)}:${emit(val, k)}`).join(",")}}`;
}
