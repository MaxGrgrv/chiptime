/**
 * Repair: salvage -> synthesize missing structure -> valid canonical .fit.
 *
 * Twin of `python/src/chiptime/repair.py`. Every synthesis lands in provenance
 * (REPAIR_*). Genuinely absent data is refused, never fabricated (taxonomy #16,
 * contract #8).
 */

import { type Mode, parse } from "./api.js";
import { RELATIVE_TS_CEILING } from "./decode.js";
import {
  type EncodableMessage,
  encodableFromMessage,
  encodableFromProfile,
  encodeMessages,
} from "./encode.js";
import { FitError, type ProvenanceEntry } from "./errors.js";
import type { Message } from "./message.js";
import type { Session } from "./model.js";
import { pyRound } from "./numeric.js";
import type { ParseResult } from "./result.js";

export class NotRepairableError extends FitError {}

/** A repaired file plus the proof of what repair did. */
export interface RepairResult {
  /** The complete, valid `.fit` bytes — write them to disk as-is. */
  data: Uint8Array;
  provenance: ProvenanceEntry[];
  /** Self-check: the output re-parsed in strict mode. */
  outputStrictOk: boolean;
  /** The salvage parse of the *input*, for inspection. */
  parseResult: ParseResult | null;
}

function p(code: string, detail: string): ProvenanceEntry {
  return { code, action: "synthesized", scope: "repair", detail, byteOffset: null, data: {} };
}

export function repair(src: Uint8Array, options: { mode?: Mode } = {}): RepairResult {
  const mode = options.mode ?? "lenient";
  const parsed = parse(src, { mode });
  const part = parsed.parts.find((pt) => pt.fileType === "activity");
  const activity = part?.activity as { sessions: Session[] } | null | undefined;
  if (
    part === undefined ||
    activity === null ||
    activity === undefined ||
    activity.sessions.length === 0
  ) {
    throw new NotRepairableError(
      "REPAIR_NOTHING_TO_SALVAGE",
      "no activity records or session survive parsing; the data is genuinely absent and will not be fabricated",
      { suggestion: "run `chiptime parse --mode forensic` to inspect what remains" },
    );
  }

  const prov: ProvenanceEntry[] = [];
  const msgs = [...part.messages];
  const session = activity.sessions[0] as Session;

  const has = (gnum: number): boolean => msgs.some((m) => m.globalNum === gnum);

  const front: EncodableMessage[] = [];
  const tail: EncodableMessage[] = [];

  // file_id (synthesize if absent — #102)
  const fileIdMsgs = msgs.filter((m) => m.globalNum === 0);
  const [firstT, lastT] = bounds(session, msgs);
  if (fileIdMsgs.length === 0) {
    front.push(
      encodableFromProfile(0, {
        type: "activity",
        manufacturer: "development",
        time_created: firstT,
      }),
    );
    prov.push(p("REPAIR_FILE_ID_SYNTHESIZED", "no file_id message; synthesized (type=activity)"));
  }

  front.push(encodableFromProfile(49, {})); // file_creator marker (empty is valid)

  if (!has(21) && session.records.time.length > 0) {
    tail.push(encodableFromProfile(21, { timestamp: firstT, event: "timer", event_type: "start" }));
    tail.push(
      encodableFromProfile(21, { timestamp: lastT, event: "timer", event_type: "stop_all" }),
    );
    prov.push(
      p(
        "REPAIR_EVENTS_SYNTHESIZED",
        "no timer events; start/stop_all synthesized at record bounds",
      ),
    );
  }

  if (!has(19)) {
    tail.push(summaryMessage(19, session, firstT, lastT, true));
    prov.push(p("REPAIR_LAP_SYNTHESIZED", "no lap message; one covering lap synthesized"));
  }

  if (!has(18)) {
    tail.push(summaryMessage(18, session, firstT, lastT, false));
    prov.push(
      p(
        "REPAIR_SESSION_SYNTHESIZED",
        `no session message; synthesized from ${session.records.time.length} salvaged record(s) (#95)`,
      ),
    );
  }

  if (!has(34)) {
    // Python's `or`: 0.0 falls through, exactly like JS `||` (and unlike `??`).
    const timer = session.derived.timerTimeS || session.derived.elapsedTimeS;
    const values: Record<string, unknown> = {
      timestamp: lastT,
      num_sessions: 1,
      type: "manual",
      event: "activity",
      event_type: "stop",
    };
    if (timer !== null) values.total_timer_time = timer;
    tail.push(encodableFromProfile(34, values));
    prov.push(p("REPAIR_ACTIVITY_SYNTHESIZED", "no activity message; synthesized"));
  }

  // Stable sort putting file_id first, as Python's key=0/1 sort does.
  const cleaned: Message[] = msgs
    .map((m, i) => [m, i] as [Message, number])
    .sort((a, b) => {
      const ka = a[0].globalNum === 0 ? 0 : 1;
      const kb = b[0].globalNum === 0 ? 0 : 1;
      return ka !== kb ? ka - kb : a[1] - b[1];
    })
    .map(([m]) => (m.globalNum === 34 ? dropBadLocalTimestamp(m, prov) : m));

  const body = cleaned.map((m) => encodableFromMessage(m));
  prov.push(p("REPAIR_REENCODED", "re-encoded to canonical wire form; all CRCs recomputed"));

  const ordered = fileIdMsgs.length
    ? [...body.slice(0, 1), ...front, ...body.slice(1), ...tail]
    : [...front, ...body, ...tail];
  const data = encodeMessages(ordered);
  const check = parse(data, { mode: "strict" });
  return { data, provenance: prov, outputStrictOk: check.ok, parseResult: parsed };
}

/**
 * #37 repair leg: never re-emit an impossible local_timestamp; an honest absence
 * (invalid sentinel) beats a wrong-but-plausible value.
 */
function dropBadLocalTimestamp(m: Message, prov: ProvenanceEntry[]): Message {
  const lt = m.fields.get("local_timestamp");
  const ts = m.fields.get("timestamp");
  if (lt === undefined || typeof lt.raw !== "number" || lt.raw === 0xffffffff) return m;
  let bad = lt.raw < RELATIVE_TS_CEILING;
  if (!bad && ts !== undefined && typeof ts.raw === "number") {
    bad = Math.abs(lt.raw - ts.raw) > 26 * 3600;
  }
  if (!bad) return m;
  const fields = new Map(m.fields);
  fields.set("local_timestamp", { ...lt, value: null, raw: null });
  prov.push({
    code: "REPAIR_LOCAL_TIMESTAMP_DROPPED",
    action: "dropped",
    scope: "repair",
    detail: `activity.local_timestamp raw ${lt.raw} is impossible for any real timezone; omitted from the repaired file (GC rejection class, #37)`,
    byteOffset: null,
    data: {},
  });
  return { ...m, fields };
}

function bounds(session: Session, msgs: Message[]): [number, number] {
  // Model times are already FIT seconds; Python converts datetimes back here.
  const times = session.records.time.filter((t): t is number => t !== null);
  if (times.length > 0) {
    return [Math.trunc(times[0] as number), Math.trunc(times[times.length - 1] as number)];
  }
  for (const m of msgs) {
    // summary-only activities: bounds from session message raws
    if (m.globalNum === 18) {
      const st = m.fields.get("start_time")?.raw;
      const ts = m.fields.get("timestamp")?.raw;
      if (typeof st === "number") {
        return [st, typeof ts === "number" ? ts : st];
      }
    }
  }
  throw new NotRepairableError(
    "REPAIR_NOTHING_TO_SALVAGE",
    "no usable timestamps to anchor repair",
  );
}

function summaryMessage(
  gnum: number,
  s: Session,
  firstT: number,
  lastT: number,
  lap: boolean,
): EncodableMessage {
  const values: Record<string, unknown> = {
    timestamp: lastT,
    start_time: firstT,
    message_index: 0,
    event: lap ? "lap" : "session",
    event_type: "stop",
  };
  const der = s.derived;
  if (der.elapsedTimeS !== null) values.total_elapsed_time = der.elapsedTimeS;
  // Python: `if (der.timer_time_s or der.elapsed_time_s) is not None` — `or` skips 0.0.
  const timerish = der.timerTimeS || der.elapsedTimeS;
  if (timerish !== null) values.total_timer_time = timerish;
  if (der.distanceM !== null) values.total_distance = der.distanceM;
  if (!lap) {
    if (s.sport && !s.sport.startsWith("unknown")) values.sport = s.sport;
    const pairs: [string, string, string][] = [
      ["heart_rate", "avg_heart_rate", "max_heart_rate"],
      ["power", "avg_power", "max_power"],
      ["cadence", "avg_cadence", "max_cadence"],
    ];
    for (const [key, avgName, maxName] of pairs) {
      const av = der.avg.get(key);
      if (av !== undefined) values[avgName] = pyRound(av);
      const mx = der.max.get(key);
      if (mx !== undefined) values[maxName] = pyRound(mx);
    }
    const avgSpeed = der.avg.get("speed");
    if (avgSpeed !== undefined) values.avg_speed = avgSpeed;
    const maxSpeed = der.max.get("speed");
    if (maxSpeed !== undefined) values.max_speed = maxSpeed;
    values.first_lap_index = 0;
    values.num_laps = 1;
  }
  return encodableFromProfile(gnum, values);
}
