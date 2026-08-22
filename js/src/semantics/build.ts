/**
 * Assemble the canonical Activity model from decoded messages.
 *
 * Twin of `python/src/chiptime/semantics/build.py`. Order-independent by
 * construction (contract #9): everything is bucketed first, then bound by time —
 * never by position in the file. Summary-first and summary-last layouts produce
 * identical models (taxonomy #50).
 *
 * Times are FIT seconds throughout; see `model.ts` for why `Date` never appears.
 */

import { RELATIVE_TS_CEILING } from "../decode.js";
import type { Diagnostic, ProvenanceEntry } from "../errors.js";
import type { Message } from "../message.js";
import {
  type Activity,
  type Event,
  type FitTime,
  type Lap,
  type Length,
  type Records,
  type Session,
  type Stream,
  type Totals,
  emptyActivity,
  emptyRecords,
  emptyTotals,
  getStream,
  newSession,
} from "../model.js";
import { pySum } from "../numeric.js";
import { classifyGaps } from "./gaps.js";
import { gatePositions } from "./plausibility.js";
import { deriveAscentDescent, lapChecks, reconcile, sensorFlags, swimChecks } from "./reconcile.js";
import { buildTimerState, movingSeconds, timerSeconds } from "./timers.js";

const FLOOR_2010_FIT = 631238400; // 2010-01-01T00:00:00Z in FIT seconds
const CREATION_DRIFT_MAX_S = 7 * 86400; // ADR-0005 §2
const MAX_REAL_OFFSET_S = 26 * 3600; // ADR-0005 §4

/** Streams where element-wise avg/max is meaningless. */
const AVGMAX_EXCLUDE = new Set(["position_lat", "position_long", "distance", "activity_type"]);

const ENHANCED_PAIRS: [string, string][] = [
  ["speed", "enhanced_speed"],
  ["altitude", "enhanced_altitude"],
];

function get(m: Message, name: string): unknown {
  return m.fields.get(name)?.value ?? null;
}

function getRaw(m: Message, name: string): unknown {
  return m.fields.get(name)?.raw ?? null;
}

/**
 * Wire timestamp to a model time.
 *
 * Device-relative (power-on) time is NOT a date; resurrecting it from raws would
 * fabricate 1990 wall-clock times (F22, fitparse#3/#6).
 */
function dt(fitSeconds: unknown): FitTime {
  if (typeof fitSeconds !== "number" || !Number.isInteger(fitSeconds)) return null;
  if (fitSeconds < RELATIVE_TS_CEILING) return null;
  return fitSeconds;
}

function num(v: unknown): number | null {
  return typeof v === "number" && !Number.isNaN(v) ? v : null;
}

function sportStr(v: unknown): string {
  if (typeof v === "string") return v;
  if (v === null || v === undefined) return "unknown";
  return `unknown_${String(v)}`;
}

export interface BuildOptions {
  skippedRanges?: [number, number][];
  forensic?: boolean;
}

export function buildActivity(
  messages: Message[],
  warnings: Diagnostic[],
  provenance: ProvenanceEntry[],
  scope: string,
  options: BuildOptions = {},
): Activity {
  const skippedRanges = options.skippedRanges ?? [];
  const forensic = options.forensic ?? false;

  let records = messages.filter((m) => m.globalNum === 20);
  records = sortedRecords(records, provenance, scope);
  timeSanityFlags(records, messages, warnings, scope);
  const sessionMsgs = messages.filter((m) => m.globalNum === 18);
  const lapMsgs = messages.filter((m) => m.globalNum === 19);
  const lengthMsgs = messages.filter((m) => m.globalNum === 101);
  const eventMsgs = messages.filter((m) => m.globalNum === 21);

  const activity = emptyActivity();

  for (const m of messages) {
    if (m.globalNum === 23 && activity.device === null) {
      activity.device = {
        manufacturer: (get(m, "manufacturer") as string | number | null) ?? null,
        product: (get(m, "product") as number | null) ?? null,
        productName: (get(m, "product_name") as string | null) ?? null,
        serialNumber: (get(m, "serial_number") as number | null) ?? null,
        softwareVersion: num(get(m, "software_version")),
      };
    } else if (m.globalNum === 3 && activity.athlete === null) {
      activity.athlete = {
        friendlyName: (get(m, "friendly_name") as string | null) ?? null,
        gender: (get(m, "gender") as string | null) ?? null,
        age: (get(m, "age") as number | null) ?? null,
        weightKg: num(get(m, "weight")),
        heightM: num(get(m, "height")),
      };
    } else if (m.globalNum === 34 && activity.localTimestamp === null) {
      const lt = get(m, "local_timestamp");
      activity.localTimestamp = typeof lt === "string" ? lt : null;
      localOffset(m, activity, warnings, scope);
    }
  }

  for (const m of messages) {
    if (m.globalNum === 78) {
      // hrv: RR interval arrays, never dropped (#72)
      const t = get(m, "time");
      if (Array.isArray(t)) {
        for (const v of t) if (typeof v === "number") activity.hrvIntervalsS.push(v);
      } else if (typeof t === "number") {
        activity.hrvIntervalsS.push(t);
      }
    }
  }

  activity.events = eventMsgs.map((m): Event => {
    const data = get(m, "data");
    return {
      time: dt(getRaw(m, "timestamp")),
      event: (get(m, "event") as string | number | null) ?? null,
      eventType: (get(m, "event_type") as string | number | null) ?? null,
      data: typeof data === "number" && Number.isInteger(data) ? data : null,
    };
  });

  let sessions = sessionMsgs.map(sessionShell);
  // Python's key is (start_time is None, start_time): nulls last, stable otherwise.
  sessions = sessions
    .map((s, i) => [s, i] as [Session, number])
    .sort((a, b) => {
      const an = a[0].startTime === null;
      const bn = b[0].startTime === null;
      if (an !== bn) return an ? 1 : -1;
      if (!an && !bn) {
        const d = (a[0].startTime as number) - (b[0].startTime as number);
        if (d !== 0) return d;
      }
      return a[1] - b[1];
    })
    .map(([s]) => s);

  if (sessions.length === 0 && records.length > 0) {
    // Session rebuild (#95) — the repair every crashed upload needs.
    const sportMsg = messages.find((m) => m.globalNum === 12);
    const first = dt(getRaw(records[0] as Message, "timestamp"));
    const last = dt(getRaw(records[records.length - 1] as Message, "timestamp"));
    const s = newSession(sportMsg ? sportStr(get(sportMsg, "sport")) : "unknown", null);
    s.startTime = first;
    s.endTime = last;
    s.rebuilt = true;
    sessions = [s];
    provenance.push({
      code: "SESSION_REBUILT",
      action: "synthesized",
      scope,
      detail: `no session message present; session synthesized from ${records.length} record(s)`,
      byteOffset: null,
      data: { records: records.length },
    });
  }
  if (sessions.length === 0) return activity; // nothing to model (honest, #8/#16)

  if (sessionMsgs.length > 0 && !messages.some((m) => m.globalNum === 34)) {
    warnings.push({
      code: "ACTIVITY_MESSAGE_MISSING",
      detail: "no activity message present (taxonomy #96); repair (M2) can synthesize one",
      scope,
    });
  }
  const actMsg = messages.find((m) => m.globalNum === 34);
  const declaredN = actMsg ? get(actMsg, "num_sessions") : null;
  if (
    typeof declaredN === "number" &&
    Number.isInteger(declaredN) &&
    declaredN !== sessions.length
  ) {
    warnings.push({
      code: "NUM_SESSIONS_MISMATCH",
      detail: `activity declares ${declaredN} session(s); file contains ${sessions.length}`,
      scope,
    });
  }

  const buckets = assign(records, lapMsgs, lengthMsgs, sessions, warnings);
  const manufacturer =
    messages.find((m) => m.globalNum === 0) !== undefined
      ? get(messages.find((m) => m.globalNum === 0) as Message, "manufacturer")
      : null;

  for (let si = 0; si < sessions.length; si++) {
    const s = sessions[si] as Session;
    const bucket = buckets[si] as Message[];
    s.records = buildStreams(bucket, warnings, provenance, scope);
    const ev = sessionEvents(activity.events, s, sessions.length);
    const times = s.records.time;
    const firstT = times.find((t) => t !== null) ?? null;
    let lastT: number | null = null;
    for (let i = times.length - 1; i >= 0; i--) {
      if (times[i] !== null && times[i] !== undefined) {
        lastT = times[i] as number;
        break;
      }
    }
    const state = buildTimerState(ev, firstT, lastT, warnings, provenance, scope);
    s.derived.timerTimeS = timerSeconds(state);
    const speed = getStream(s.records, "speed");
    s.derived.movingTimeS = movingSeconds(times, speed ? speed.values : null, state);
    activity.gaps.push(
      ...classifyGaps(
        times,
        bucket.map((m) => m.byteOffset),
        state,
        ev,
        skippedRanges,
      ),
    );
    derive(s);
    deriveRelativeElapsed(s, bucket);
    gatePositions(s, {
      forensic,
      virtual: manufacturer === "zwift" || s.subSport === "virtual_activity",
      provenance,
      scope,
    });
    deriveAscentDescent(s);
    reconcile(s, warnings, scope);
    sensorFlags(s, warnings, scope);
    swimChecks(s, warnings, scope);
    lapChecks(s, warnings, scope);
  }

  activity.sessions = sessions;
  return activity;
}

/** ADR-0005 §1: stable sort with carry-forward keys; reorders recorded. */
function sortedRecords(
  records: Message[],
  provenance: ProvenanceEntry[],
  scope: string,
): Message[] {
  let last = -1;
  let isSorted = true;
  for (const m of records) {
    const ts = getRaw(m, "timestamp");
    if (typeof ts === "number" && Number.isInteger(ts)) {
      if (ts < last) {
        isSorted = false;
        break;
      }
      last = ts;
    }
  }
  if (isSorted) return records; // the overwhelmingly common case, one cheap scan

  const keys: [number, number][] = [];
  last = -1;
  records.forEach((m, i) => {
    const ts = getRaw(m, "timestamp");
    if (typeof ts === "number" && Number.isInteger(ts)) last = ts;
    keys.push([last, i]);
  });
  const order = records
    .map((_, i) => i)
    .sort((a, b) => {
      const ka = keys[a] as [number, number];
      const kb = keys[b] as [number, number];
      return ka[0] !== kb[0] ? ka[0] - kb[0] : ka[1] - kb[1];
    });
  if (order.every((v, i) => v === i)) return records;
  let moved = 0;
  order.forEach((i, pos) => {
    if (pos !== i) moved++;
  });
  provenance.push({
    code: "RECORDS_REORDERED",
    action: "reinterpreted",
    scope,
    detail: `${moved} record(s) were out of chronological order; stably sorted (equal timestamps keep file order)`,
    byteOffset: null,
    data: { moved },
  });
  return order.map((i) => records[i] as Message);
}

function timeSanityFlags(
  records: Message[],
  messages: Message[],
  warnings: Diagnostic[],
  scope: string,
): void {
  const raws: number[] = [];
  for (const m of records) {
    const ts = getRaw(m, "timestamp");
    if (typeof ts === "number" && Number.isInteger(ts) && ts >= RELATIVE_TS_CEILING) raws.push(ts);
  }
  if (raws.length === 0) return;
  if (Math.min(...raws) < FLOOR_2010_FIT) {
    warnings.push({
      code: "UNRELIABLE_ABSOLUTE_TIME",
      detail:
        "record timestamps predate 2010; the device likely never acquired GPS time — relative timeline preserved (ADR-0005 §3)",
      scope,
    });
  }
  const fileId = messages.find((m) => m.globalNum === 0);
  const created = fileId ? getRaw(fileId, "time_created") : null;
  if (
    typeof created === "number" &&
    Number.isInteger(created) &&
    Math.max(...raws) > created + CREATION_DRIFT_MAX_S
  ) {
    warnings.push({
      code: "TIMESTAMPS_AFTER_CREATION",
      detail:
        "record timestamps postdate file_id.time_created by more than 7 days; device clock suspect (ADR-0005 §2)",
      scope,
    });
  }
}

/** ADR-0005 §4: validate the local/UTC pair (taxonomy #37, Zwift 1989 bug). */
function localOffset(m: Message, activity: Activity, warnings: Diagnostic[], scope: string): void {
  const tsRaw = getRaw(m, "timestamp");
  const ltRaw = getRaw(m, "local_timestamp");
  if (typeof ltRaw !== "number" || typeof tsRaw !== "number") return;
  if (!Number.isInteger(ltRaw) || !Number.isInteger(tsRaw)) return;
  if (ltRaw === 0xffffffff || tsRaw === 0xffffffff) return; // sentinel = honestly absent
  if (ltRaw < RELATIVE_TS_CEILING || tsRaw < RELATIVE_TS_CEILING) {
    warnings.push({
      code: "LOCAL_TIMESTAMP_IMPLAUSIBLE",
      detail: `activity.local_timestamp raw ${ltRaw} is device-relative (the Zwift 1989 bug class); utc offset unavailable`,
      scope,
    });
    return;
  }
  const off = ltRaw - tsRaw;
  if (Math.abs(off) > MAX_REAL_OFFSET_S) {
    warnings.push({
      code: "LOCAL_TIMESTAMP_IMPLAUSIBLE",
      detail: `local-UTC offset of ${off} s is impossible for any real timezone`,
      scope,
    });
    return;
  }
  activity.utcOffsetS = off;
}

function sessionEvents(events: Event[], s: Session, nSessions: number): Event[] {
  if (nSessions === 1 || s.startTime === null || s.endTime === null) return events;
  const start = s.startTime;
  const end = s.endTime;
  return events.filter((e) => e.time !== null && e.time >= start && e.time <= end);
}

function sessionShell(m: Message): Session {
  const start = dt(getRaw(m, "start_time"));
  const elapsed = num(get(m, "total_elapsed_time"));
  // #50: end = start + elapsed. The summary's own timestamp is a WRITE time and
  // must never define bounds.
  const end = start !== null && elapsed !== null ? start + elapsed : null;
  const declared: Totals = {
    ...emptyTotals(),
    elapsedTimeS: elapsed,
    timerTimeS: num(get(m, "total_timer_time")),
    distanceM: num(get(m, "total_distance")),
    ascentM: num(get(m, "total_ascent")),
    descentM: num(get(m, "total_descent")),
    caloriesKcal: num(get(m, "total_calories")),
  };
  const pairs: [string, string, string][] = [
    ["speed", "avg_speed", "max_speed"],
    ["heart_rate", "avg_heart_rate", "max_heart_rate"],
    ["cadence", "avg_cadence", "max_cadence"],
    ["power", "avg_power", "max_power"],
  ];
  for (const [key, avgF, maxF] of pairs) {
    let av = key === "speed" ? num(get(m, `enhanced_${avgF}`)) : null;
    av = av ?? num(get(m, avgF));
    let mx = key === "speed" ? num(get(m, `enhanced_${maxF}`)) : null;
    mx = mx ?? num(get(m, maxF));
    if (av !== null) declared.avg.set(key, av);
    if (mx !== null) declared.max.set(key, mx);
  }
  const subSport = get(m, "sub_sport");
  const s = newSession(sportStr(get(m, "sport")), typeof subSport === "string" ? subSport : null);
  s.startTime = start;
  s.endTime = end;
  s.declared = declared;
  return s;
}

function assign(
  records: Message[],
  lapMsgs: Message[],
  lengthMsgs: Message[],
  sessions: Session[],
  warnings: Diagnostic[],
): Message[][] {
  const buckets: Message[][] = sessions.map(() => []);

  const owner = (t: FitTime): number => {
    if (sessions.length === 1 || t === null) return 0;
    for (let i = 0; i < sessions.length; i++) {
      const s = sessions[i] as Session;
      if (s.startTime !== null && s.endTime !== null && s.startTime <= t && t <= s.endTime) {
        return i;
      }
    }
    // nearest by start; Python's min() keeps the first minimum on ties
    let bestI = 0;
    let bestKey = Number.POSITIVE_INFINITY;
    for (let i = 0; i < sessions.length; i++) {
      const st = (sessions[i] as Session).startTime;
      const key = st !== null ? Math.abs(t - st) : 1e18;
      if (key < bestKey) {
        bestKey = key;
        bestI = i;
      }
    }
    return bestI;
  };

  let outside = 0;
  for (const m of records) {
    const t = dt(getRaw(m, "timestamp"));
    const i = owner(t);
    const s = sessions[i] as Session;
    const inBounds =
      t !== null &&
      s.startTime !== null &&
      s.endTime !== null &&
      s.startTime <= t &&
      t <= s.endTime;
    if (sessions.length > 1 && t !== null && !inBounds) outside++;
    (buckets[i] as Message[]).push(m);
  }
  if (outside) {
    warnings.push({
      code: "RECORDS_OUTSIDE_SESSIONS",
      detail: `${outside} record(s) fall outside every session's declared bounds; attached to the nearest session`,
      scope: "activity",
    });
  }

  for (const m of lapMsgs) {
    const start = dt(getRaw(m, "start_time"));
    const elapsed = num(get(m, "total_elapsed_time"));
    const end = start !== null && elapsed !== null ? start + elapsed : null;
    const mi = get(m, "message_index");
    const sport = get(m, "sport");
    const lap: Lap = {
      messageIndex: typeof mi === "number" && Number.isInteger(mi) ? mi : null,
      startTime: start,
      endTime: end,
      declared: {
        ...emptyTotals(),
        elapsedTimeS: elapsed,
        timerTimeS: num(get(m, "total_timer_time")),
        distanceM: num(get(m, "total_distance")),
        caloriesKcal: num(get(m, "total_calories")),
      },
      sport: typeof sport === "string" ? sport : null,
    };
    (sessions[owner(start)] as Session).laps.push(lap);
  }

  for (const m of lengthMsgs) {
    const start = dt(getRaw(m, "start_time"));
    const elapsed = num(get(m, "total_elapsed_time"));
    const end = start !== null && elapsed !== null ? start + elapsed : null;
    const strokes = get(m, "total_strokes");
    const lengthType = get(m, "length_type");
    const stroke = get(m, "swim_stroke");
    const len: Length = {
      startTime: start,
      endTime: end,
      lengthType: typeof lengthType === "string" ? lengthType : null,
      swimStroke: typeof stroke === "string" ? stroke : null,
      totalStrokes: typeof strokes === "number" && Number.isInteger(strokes) ? strokes : null,
      totalElapsedTimeS: elapsed,
    };
    (sessions[owner(start)] as Session).lengths.push(len);
  }

  return buckets;
}

function toHex(u8: Uint8Array): string {
  let out = "";
  for (const b of u8) out += b.toString(16).padStart(2, "0");
  return out;
}

function buildStreams(
  records: Message[],
  warnings: Diagnostic[],
  provenance: ProvenanceEntry[],
  scope: string,
): Records {
  const out = emptyRecords();
  const order: string[] = []; // first-appearance stream order (deterministic)
  const meta = new Map<string, [string | null, string]>();
  const columns = new Map<string, unknown[]>();

  records.forEach((m, i) => {
    out.time.push(dt(getRaw(m, "timestamp")));
    for (const [fname, fv] of m.fields) {
      if (fname === "timestamp") continue;
      let sname = fname;
      let source = "native";
      if (fv.developer !== null) {
        if (fv.developer.canonicalName) sname = fv.developer.canonicalName;
        source = fv.developer.vendor ? `developer:${fv.developer.vendor}` : "developer";
      }
      const existing = meta.get(sname);
      if (existing !== undefined && existing[1] !== source) sname = `${sname}_dev`;
      if (!columns.has(sname)) {
        order.push(sname);
        meta.set(sname, [fv.units, source]);
        columns.set(sname, new Array(i).fill(null));
      }
      const value = fv.value instanceof Uint8Array ? toHex(fv.value) : fv.value;
      (columns.get(sname) as unknown[]).push(value);
    }
    for (const sname of order) {
      const col = columns.get(sname) as unknown[];
      if (col.length <= i) col.push(null);
    }
  });

  mergeEnhanced(order, meta, columns, warnings, provenance, scope);

  for (const sname of order) {
    const [units, source] = meta.get(sname) as [string | null, string];
    const stream: Stream = { name: sname, units, values: columns.get(sname) as unknown[], source };
    out.streams.set(sname, stream);
  }
  return out;
}

/** Taxonomy #28: one stream per quantity; enhanced wins; never both silently. */
function mergeEnhanced(
  order: string[],
  meta: Map<string, [string | null, string]>,
  columns: Map<string, unknown[]>,
  warnings: Diagnostic[],
  provenance: ProvenanceEntry[],
  scope: string,
): void {
  for (const [base, enhanced] of ENHANCED_PAIRS) {
    if (!columns.has(enhanced)) continue;
    const evals = columns.get(enhanced) as unknown[];
    columns.delete(enhanced);
    order.splice(order.indexOf(enhanced), 1);
    const emeta = meta.get(enhanced) as [string | null, string];
    meta.delete(enhanced);
    if (!columns.has(base)) {
      columns.set(base, evals);
      order.push(base);
      meta.set(base, emeta);
      continue;
    }
    const bvals = columns.get(base) as unknown[];
    let disagreements = 0;
    const merged: unknown[] = [];
    for (let i = 0; i < evals.length; i++) {
      const e = evals[i];
      const b = bvals[i];
      if (typeof e === "number" && typeof b === "number" && Math.abs(e - b) > 0.01) {
        disagreements++;
      }
      merged.push(e !== null && e !== undefined ? e : b);
    }
    columns.set(base, merged);
    if (disagreements) {
      warnings.push({
        code: "ENHANCED_PAIR_DISAGREES",
        detail: `${base} and ${enhanced} disagree on ${disagreements} record(s); enhanced values kept`,
        scope,
      });
    }
    provenance.push({
      code: "ENHANCED_PAIR_MERGED",
      action: "reinterpreted",
      scope,
      detail: `${enhanced} merged into the ${base} stream (enhanced preferred)`,
      byteOffset: null,
      data: { disagreements },
    });
  }
}

/**
 * Taxonomy #39: when the device never had wall-clock time (all timestamps
 * device-relative), the RELATIVE timeline is still real — derive durations from raw
 * deltas instead of leaving everything null (fitparse#3/#6 class).
 */
function deriveRelativeElapsed(s: Session, bucket: Message[]): void {
  if (s.derived.elapsedTimeS !== null) return;
  const raws: number[] = [];
  for (const m of bucket) {
    const ts = getRaw(m, "timestamp");
    if (typeof ts === "number" && Number.isInteger(ts) && ts !== 0xffffffff) raws.push(ts);
  }
  if (raws.length >= 2) {
    const first = raws[0] as number;
    const last = raws[raws.length - 1] as number;
    if (last >= first) s.derived.elapsedTimeS = last - first;
  }
}

function derive(s: Session): void {
  const times = s.records.time.filter((t): t is number => t !== null);
  if (times.length >= 2) {
    s.derived.elapsedTimeS = (times[times.length - 1] as number) - (times[0] as number);
  }
  const dist = getStream(s.records, "distance");
  if (dist !== undefined) {
    const present = dist.values.filter((v): v is number => typeof v === "number");
    if (present.length >= 2) {
      s.derived.distanceM = (present[present.length - 1] as number) - (present[0] as number);
    }
  }
  for (const [name, stream] of s.records.streams) {
    if (AVGMAX_EXCLUDE.has(name)) continue;
    const nums = stream.values.filter((v): v is number => typeof v === "number");
    if (nums.length > 0) {
      // pySum, not a loop of additions: CPython's sum() runs compensated
      // (Neumaier) summation on floats, and the difference lands in the average.
      s.derived.avg.set(name, pySum(nums) / nums.length);
      let mx = nums[0] as number;
      for (const v of nums) if (v > mx) mx = v;
      s.derived.max.set(name, mx);
    }
  }
}
