/**
 * Crop an activity without letting the file lie about itself.
 *
 * Twin of `python/src/chiptime/trim.py` (F27). Removing records is easy; the hard
 * part is that every number computed *from* those records — session totals,
 * activity totals, averages — is wrong the moment they disappear. So trimming is
 * two acts: filter the records, then rebuild everything that depended on them,
 * using the same semantic layer that computes totals during a normal parse.
 */

import { type Mode, parse } from "./api.js";
import { FIT_EPOCH_UNIX } from "./decode.js";
import {
  type EncodableMessage,
  encodableFromMessage,
  encodableFromProfile,
  encodeMessages,
} from "./encode.js";
import { type Diagnostic, FitError, type ProvenanceEntry } from "./errors.js";
import { type Message, get, getRaw } from "./message.js";
import type { Session } from "./model.js";
import { summaryMessage } from "./repair.js";
import type { ParseResult } from "./result.js";
import { buildActivity } from "./semantics/build.js";

const RECORD = 20;
const LAP = 19;
const SESSION = 18;
const EVENT = 21;
const ACTIVITY = 34;
const LENGTH = 101;

// Messages whose content is derived from records; always rebuilt after a trim
const REBUILT: readonly number[] = [SESSION, ACTIVITY];

const RELATIVE = /^([+-])(\d+(?:\.\d+)?)([smh]?)$/;
const UNIT_SECONDS: Readonly<Record<string, number>> = { s: 1, m: 60, h: 3600, "": 1 };

/** A trim cannot be performed; no bytes are written. */
export class TrimError extends FitError {}

/** The cropped file plus an account of what was removed and rebuilt. */
export interface TrimResult {
  /** The trimmed `.fit` bytes. */
  data: Uint8Array;
  /** What was dropped and what was rebuilt, with counts. */
  provenance: ProvenanceEntry[];
  /** Records inside the keep-window. */
  recordsKept: number;
  /** Records removed by the trim. */
  recordsDropped: number;
  /** Non-fatal observations carried from the rebuild. */
  warnings: Diagnostic[];
  /** Self-check — the output re-parsed in strict mode. */
  outputStrictOk: boolean;
  /** The parse of the *input*, for inspection. */
  parseResult: ParseResult | null;
}

function prov(
  code: string,
  scope: string,
  detail: string,
  data: Record<string, unknown>,
): ProvenanceEntry {
  return { code, action: "dropped", scope, detail, byteOffset: null, data };
}

function pyRepr(v: unknown): string {
  if (v === null || v === undefined) return "None";
  if (typeof v === "string") return `'${v}'`;
  return String(v);
}

/** `days_from_civil` — Hinnant's inverse of the decoder's `civilFromUnix`. */
function daysFromCivil(year: number, m: number, d: number): number {
  const y = year - (m <= 2 ? 1 : 0);
  const era = Math.floor(y / 400);
  const yoe = y - era * 400;
  const doy = Math.trunc((153 * (m + (m > 2 ? -3 : 9)) + 2) / 5) + d - 1;
  const doe = yoe * 365 + Math.trunc(yoe / 4) - Math.trunc(yoe / 100) + doy;
  return era * 146097 + doe - 719468;
}

/**
 * ISO-8601 → unix seconds, `Date`-free.
 *
 * A deliberate, documented deviation from the Python twin: CPython's
 * `fromisoformat(...).timestamp()` interprets a *naive* string in the machine's
 * local timezone — same input, different output per host. Here a naive string is
 * read as UTC: deterministic beats environment-dependent (ADR-0009 §6 spirit).
 * Offset-aware strings agree exactly on both sides.
 */
function isoToUnix(text: string): number | null {
  const m =
    /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,6}))?)?)?(Z|[+-]\d{2}:\d{2}(?::\d{2})?)?$/.exec(
      text,
    );
  if (m === null) return null;
  const [, ys, ms, ds, hh, mm, ss, frac, off] = m;
  const y = Number(ys);
  const mo = Number(ms);
  const d = Number(ds);
  if (mo < 1 || mo > 12 || d < 1 || d > 31) return null;
  const h = hh !== undefined ? Number(hh) : 0;
  const mi = mm !== undefined ? Number(mm) : 0;
  const s = ss !== undefined ? Number(ss) : 0;
  if (h > 23 || mi > 59 || s > 59) return null;
  const fracS = frac !== undefined ? Number(`0.${frac}`) : 0;
  let offS = 0;
  if (off !== undefined && off !== "Z") {
    const sign = off.startsWith("-") ? -1 : 1;
    const parts = off.slice(1).split(":").map(Number);
    offS = sign * ((parts[0] as number) * 3600 + (parts[1] as number) * 60 + (parts[2] ?? 0));
  }
  // int(dt.timestamp()) truncates toward zero.
  return Math.trunc(daysFromCivil(y, mo, d) * 86400 + h * 3600 + mi * 60 + s + fracS - offS);
}

/**
 * Resolve a bound to FIT seconds.
 *
 * Accepts an absolute ISO-8601 string, a raw FIT-seconds number, or a relative
 * offset — `"+5m"` meaning five minutes after the activity starts, `"-10m"`
 * meaning ten minutes before it ends.
 */
function resolveBound(value: string | number | null, first: number, last: number): number | null {
  if (value === null) return null;
  if (typeof value === "number") return value;
  const text = value.trim();
  const rel = RELATIVE.exec(text);
  if (rel !== null) {
    const [, sign, amount, unit] = rel as unknown as [string, string, string, string];
    const seconds = Math.trunc(Number(amount) * (UNIT_SECONDS[unit] as number));
    return sign === "+" ? first + seconds : last - seconds;
  }
  const unix = isoToUnix(text.replace("Z", "+00:00"));
  if (unix === null) {
    throw new TrimError("TRIM_BAD_BOUND", `cannot interpret ${pyRepr(value)} as a time bound`, {
      suggestion: "use an ISO timestamp, or a relative offset like '+5m' or '-10m'",
    });
  }
  return unix - FIT_EPOCH_UNIX;
}

/** Time span of the trimmable content: records, or pool lengths for
 * length-only swim files (which carry no record messages at all). */
function activityBounds(messages: readonly Message[]): [number, number] {
  const stamps: number[] = [];
  for (const m of messages) {
    if (m.globalNum !== RECORD && m.globalNum !== LENGTH) continue;
    const ts = getRaw(m, "timestamp");
    if (typeof ts === "number" && Number.isInteger(ts)) stamps.push(ts);
  }
  if (stamps.length === 0) {
    throw new TrimError(
      "TRIM_NO_RECORDS",
      "the file has no timestamped records or lengths to trim",
      { suggestion: "run `chiptime parse` to see what the file actually contains" },
    );
  }
  return [Math.min(...stamps), Math.max(...stamps)];
}

function lapSpan(m: Message): [number, number] | null {
  const start = getRaw(m, "start_time");
  const elapsed = get(m, "total_elapsed_time");
  if (typeof start !== "number" || !Number.isInteger(start)) return null;
  if (typeof elapsed === "number") {
    return [start, start + Math.trunc(elapsed)]; // end = start + elapsed, never the write ts (#50)
  }
  const end = getRaw(m, "timestamp");
  return typeof end === "number" && Number.isInteger(end) ? [start, end] : null;
}

export interface TrimOptions {
  /** Keep records at or after this bound: ISO string, FIT seconds, or `"+5m"`
   * = five minutes after the start (cut the first five minutes). */
  after?: string | number | null;
  /** Keep records at or before this bound. `"-10m"` = ten minutes before the
   * end (cut the last ten minutes). */
  before?: string | number | null;
  /** Parse policy for reading the input. */
  mode?: Mode;
}

/**
 * Crop an activity to a time window and rebuild every derived number.
 *
 * Throws `TrimError` when no bound is given, a bound cannot be interpreted, the
 * file has no records, or the window keeps nothing. No bytes are written in any
 * of these cases.
 */
export function trim(src: Uint8Array, options: TrimOptions = {}): TrimResult {
  const after = options.after ?? null;
  const before = options.before ?? null;
  const mode = options.mode ?? "lenient";

  if (after === null && before === null) {
    throw new TrimError("TRIM_NO_WINDOW", "trim() was called without a window", {
      suggestion: "pass after= and/or before=, e.g. after='+5m'",
    });
  }

  const parsed = parse(src, { mode });
  const messages = [...parsed.messages];
  if (!messages.some((m) => m.globalNum === RECORD)) {
    // Length-only pool files carry no records, so there is nothing to rebuild
    // session totals *from* once the stale summary is dropped — and carrying a
    // stale summary forward is the lie this feature exists to prevent.
    throw new TrimError(
      "TRIM_NO_RECORDS",
      "this file has no record messages, so trimmed totals could not be " +
        "recomputed (length-only pool files are not trimmable yet)",
      {
        suggestion: "run `chiptime parse` to see what the file contains; no bytes were written",
      },
    );
  }
  const [first, last] = activityBounds(messages);
  let lo = resolveBound(after, first, last);
  let hi = resolveBound(before, first, last);
  lo = lo === null ? first : Math.max(lo, first);
  hi = hi === null ? last : Math.min(hi, last);
  if (lo > hi) {
    throw new TrimError(
      "TRIM_EMPTY_RESULT",
      `the requested window keeps nothing (after=${pyRepr(after)}, before=${pyRepr(before)})`,
      { suggestion: "widen the window; no bytes were written" },
    );
  }

  const provenance: ProvenanceEntry[] = [];
  const kept: Message[] = [];
  let droppedRecords = 0;
  let droppedLengths = 0;
  const droppedLaps: number[] = [];
  const keptLapIndices: number[] = [];
  let keptEvents = 0;

  for (const m of messages) {
    const gnum = m.globalNum;
    if (REBUILT.includes(gnum)) continue; // always rebuilt from survivors — never stale
    if (gnum === RECORD || gnum === LENGTH || gnum === EVENT) {
      const ts = getRaw(m, "timestamp");
      const inside = typeof ts === "number" && Number.isInteger(ts) && lo <= ts && ts <= hi;
      if (inside) {
        kept.push(m);
        keptEvents += gnum === EVENT ? 1 : 0;
      } else if (gnum === RECORD) {
        droppedRecords += 1;
      } else if (gnum === LENGTH) {
        droppedLengths += 1;
      }
      continue;
    }
    if (gnum === LAP) {
      const span = lapSpan(m);
      const idx = get(m, "message_index");
      if (span !== null && lo <= span[0] && span[1] <= hi) {
        kept.push(m); // wholly inside: its declared totals are still true
        if (typeof idx === "number" && Number.isInteger(idx)) keptLapIndices.push(idx);
      } else {
        droppedLaps.push(typeof idx === "number" && Number.isInteger(idx) ? idx : -1);
      }
      continue;
    }
    kept.push(m);
  }

  const recordsKept = kept.filter((m) => m.globalNum === RECORD).length;
  const lengthsKept = kept.filter((m) => m.globalNum === LENGTH).length;
  if (recordsKept === 0 && lengthsKept === 0) {
    throw new TrimError("TRIM_EMPTY_RESULT", "the requested window keeps no records or lengths", {
      suggestion: "widen the window; no bytes were written",
    });
  }

  if (droppedRecords || droppedLengths) {
    provenance.push(
      prov(
        "TRIM_RECORDS_DROPPED",
        "file",
        `dropped ${droppedRecords} record(s)${droppedLengths ? ` and ${droppedLengths} pool length(s)` : ""} outside the requested window`,
        {
          records_dropped: droppedRecords,
          lengths_dropped: droppedLengths,
          window_fit_seconds: [lo, hi],
        },
      ),
    );
  }
  if (droppedLaps.length > 0) {
    provenance.push(
      prov(
        "TRIM_LAP_DROPPED",
        "file",
        `dropped ${droppedLaps.length} lap(s) not wholly inside the window; their in-window records are kept`,
        { lap_message_indices: droppedLaps },
      ),
    );
  }

  // Rebuild derived totals from the survivors using the ordinary semantic
  // layer — the one place totals arithmetic lives (critique: no round trip).
  const warnings: Diagnostic[] = [];
  const rebuildProv: ProvenanceEntry[] = [];
  const activity = buildActivity(kept, warnings, rebuildProv, "trim");
  if (activity.sessions.length === 0) {
    throw new TrimError(
      "TRIM_EMPTY_RESULT",
      "no session could be rebuilt from the surviving records",
      { suggestion: "widen the window; no bytes were written" },
    );
  }
  const session = activity.sessions[0] as Session;

  const tail: EncodableMessage[] = [];
  if (keptEvents === 0) {
    tail.push(encodableFromProfile(EVENT, { timestamp: lo, event: "timer", event_type: "start" }));
    tail.push(
      encodableFromProfile(EVENT, { timestamp: hi, event: "timer", event_type: "stop_all" }),
    );
  }
  if (keptLapIndices.length === 0) {
    tail.push(summaryMessage(LAP, session, lo, hi, true));
  }
  tail.push(
    summaryMessage(
      SESSION,
      session,
      lo,
      hi,
      false,
      keptLapIndices.length > 0 ? Math.min(...keptLapIndices) : 0,
      keptLapIndices.length || 1,
    ),
  );
  // Python `or`: a zero timer duration falls through to elapsed.
  const timer = session.derived.timerTimeS || session.derived.elapsedTimeS;
  const activityValues: Record<string, unknown> = {
    timestamp: hi,
    num_sessions: 1,
    type: "manual",
    event: "activity",
    event_type: "stop",
  };
  if (timer !== null) activityValues.total_timer_time = timer;
  tail.push(encodableFromProfile(ACTIVITY, activityValues));
  provenance.push({
    code: "TRIM_SUMMARIES_REBUILT",
    action: "synthesized",
    scope: "file",
    detail: `session and activity totals recomputed from the ${recordsKept || lengthsKept} surviving ${recordsKept ? "record" : "length"}(s)`,
    byteOffset: null,
    data: { records_kept: recordsKept, lengths_kept: lengthsKept },
  });

  const data = encodeMessages([...kept.map((m) => encodableFromMessage(m)), ...tail]);
  let strictOk = false;
  try {
    parse(data, { mode: "strict" });
    strictOk = true;
  } catch (e) {
    if (!(e instanceof FitError)) throw e;
    strictOk = false;
  }
  return {
    data,
    provenance,
    recordsKept,
    recordsDropped: droppedRecords,
    warnings,
    outputStrictOk: strictOk,
    parseResult: parsed,
  };
}
