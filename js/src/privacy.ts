/**
 * What a file discloses, and how to remove it.
 *
 * Twin of `python/src/chiptime/privacy.py` (F28). Two verbs, because they answer
 * different questions: `reveal` — *what does this file disclose?* (read-only) —
 * and `scrub` — *remove it*, writing a file that still parses and uploads. Both
 * read one category table, so a report can never disagree with what the scrubber
 * would actually remove.
 */

import { type Mode, parse } from "./api.js";
import { encodableFromMessage, encodeMessages } from "./encode.js";
import { type Diagnostic, FitError, type ProvenanceEntry } from "./errors.js";
import { type FieldValue, type Message, get } from "./message.js";
import { pyRoundN } from "./numeric.js";
import type { ParseResult } from "./result.js";

// Coordinates in a disclosure report are rounded to this many decimals
// (~1.1 km — neighbourhood, not doorstep). A report that prints your front
// door is a footgun: these reports get pasted into the same threads the
// files do.
export const COARSE_DECIMALS = 2;

export const EARTH_RADIUS_M = 6_371_000.0;

const RECORD = 20;
const LAP = 19;
const SESSION = 18;
const POSITION_FIELDS = ["position_lat", "position_long"] as const;
const SUMMARY_POSITION_FIELDS = [
  "start_position_lat",
  "start_position_long",
  "end_position_lat",
  "end_position_long",
  "nec_lat",
  "nec_long",
  "swc_lat",
  "swc_long",
] as const;

/** A scrub cannot be performed; no bytes are written. */
export class ScrubError extends FitError {}

/**
 * A class of personal data: whole messages to drop, fields to null.
 *
 * `fieldScope` matters more than it looks: `session.max_heart_rate` is real
 * training data, `zones_target.max_heart_rate` is the athlete's configured
 * physiological maximum. Same field name, opposite meaning, so fields are only
 * treated as personal inside the messages named here. An empty scope means the
 * field is personal wherever it appears (a serial number always is).
 */
interface Category {
  readonly key: string;
  readonly label: string;
  readonly messages: ReadonlySet<string>;
  readonly fields: readonly string[];
  readonly fieldScope: ReadonlySet<string>;
}

const CATEGORIES: readonly Category[] = [
  {
    key: "identity",
    label: "who you are",
    messages: new Set(["user_profile"]),
    fields: ["friendly_name", "gender", "age", "height", "weight", "global_id"],
    fieldScope: new Set(["user_profile", "athlete", "workout"]),
  },
  {
    key: "serials",
    label: "which device this is",
    messages: new Set<string>(),
    fields: ["serial_number", "ant_device_number"],
    fieldScope: new Set<string>(),
  },
  {
    key: "body_metrics",
    label: "your physiology",
    messages: new Set(["zones_target"]),
    fields: [
      "functional_threshold_power",
      "threshold_heart_rate",
      "max_heart_rate",
      "resting_heart_rate",
      "default_max_heart_rate",
      "default_max_running_heart_rate",
      "default_max_biking_heart_rate",
      "vo2_max",
    ],
    fieldScope: new Set(["user_profile", "zones_target", "hrv", "max_met_data"]),
  },
];
const CATEGORY_KEYS = CATEGORIES.map((c) => c.key);

/** One thing the file discloses. */
export interface PrivacyFinding {
  readonly category: string;
  readonly message: string;
  readonly field: string | null;
  readonly count: number;
  readonly detail: string;
}

/** What a file discloses, by category. Coordinates are deliberately coarse. */
export class PrivacyReport {
  /** One entry per disclosing message/field, with counts. */
  findings: PrivacyFinding[] = [];
  /** Records carrying GPS coordinates. */
  positionsPresent = 0;
  /** Approximate start coordinate, rounded, or null. */
  startCoarse: [number, number] | null = null;
  /** Approximate end coordinate, rounded, or null. */
  endCoarse: [number, number] | null = null;
  /** Categories this file does not disclose at all. */
  cleanCategories: string[] = [];

  get disclosesLocation(): boolean {
    return this.positionsPresent > 0 || this.startCoarse !== null;
  }

  toDict(): Record<string, unknown> {
    return {
      findings: this.findings.map((f) => ({
        category: f.category,
        message: f.message,
        field: f.field,
        count: f.count,
        detail: f.detail,
      })),
      positions_present: this.positionsPresent,
      start_coarse: this.startCoarse ? [...this.startCoarse] : null,
      end_coarse: this.endCoarse ? [...this.endCoarse] : null,
      clean_categories: this.cleanCategories,
    };
  }
}

/** The scrubbed file plus an account of what was removed. */
export interface ScrubResult {
  /** The scrubbed `.fit` bytes. */
  data: Uint8Array;
  /** One entry per category removed, with counts. */
  provenance: ProvenanceEntry[];
  /** Non-fatal observations (e.g. every position was concealed). */
  warnings: Diagnostic[];
  /** Count of removals per category key. */
  removed: Record<string, number>;
  /** Self-check — the output re-parsed in strict mode. */
  outputStrictOk: boolean;
  /** The parse of the *input*, for inspection. */
  parseResult: ParseResult | null;
}

function num(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

function position(m: Message): [number, number] | null {
  const lat = num(get(m, POSITION_FIELDS[0]));
  const lon = num(get(m, POSITION_FIELDS[1]));
  return lat !== null && lon !== null ? [lat, lon] : null;
}

const RAD = Math.PI / 180;

function haversineM(a: [number, number], b: [number, number]): number {
  const lat1 = a[0] * RAD;
  const lon1 = a[1] * RAD;
  const lat2 = b[0] * RAD;
  const lon2 = b[1] * RAD;
  const dlat = lat2 - lat1;
  const dlon = lon2 - lon1;
  const h = Math.sin(dlat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dlon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(Math.min(1.0, h)));
}

function coarse(p: [number, number] | null): [number, number] | null {
  return p ? [pyRoundN(p[0], COARSE_DECIMALS), pyRoundN(p[1], COARSE_DECIMALS)] : null;
}

/**
 * Report what a file discloses about you. Reads only; writes nothing.
 *
 * Coordinates are rounded to ~1.1 km so the report itself is safe to share —
 * which is the whole point of having one.
 */
export function reveal(src: Uint8Array, options: { mode?: Mode } = {}): PrivacyReport {
  const mode = options.mode ?? "lenient";
  const parsed = parse(src, { mode });
  const report = new PrivacyReport();
  const counts = new Map<string, number>();
  const bump = (cat: string, msg: string, fieldName: string | null): void => {
    const key = JSON.stringify([cat, msg, fieldName]);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  };
  const positions: [number, number][] = [];

  for (const m of parsed.messages) {
    const pos = position(m);
    if (pos !== null && m.globalNum === RECORD) positions.push(pos);
    for (const cat of CATEGORIES) {
      if (cat.messages.has(m.name)) {
        bump(cat.key, m.name, null);
        continue;
      }
      if (cat.fieldScope.size > 0 && !cat.fieldScope.has(m.name)) continue;
      for (const [fname, fv] of m.fields) {
        if (cat.fields.includes(fname) && fv.value !== null) bump(cat.key, m.name, fname);
      }
    }
    if (m.globalNum === LAP || m.globalNum === SESSION) {
      for (const posField of SUMMARY_POSITION_FIELDS) {
        const summaryFv = m.fields.get(posField);
        if (summaryFv !== undefined && summaryFv.value !== null) {
          bump("location", m.name, posField);
        }
      }
    }
  }

  const entries = [...counts.entries()]
    .map(([k, count]) => {
      const [catKey, msg, foundField] = JSON.parse(k) as [string, string, string | null];
      return { catKey, msg, foundField, count };
    })
    .sort((a, b) => {
      if (a.catKey !== b.catKey) return a.catKey < b.catKey ? -1 : 1;
      if (a.msg !== b.msg) return a.msg < b.msg ? -1 : 1;
      const fa = a.foundField ?? "";
      const fb = b.foundField ?? "";
      return fa < fb ? -1 : fa > fb ? 1 : 0;
    });
  for (const e of entries) {
    const detail =
      e.foundField === null
        ? `${e.msg} message present (${e.count} time(s))`
        : `${e.msg}.${e.foundField} present in ${e.count} message(s)`;
    report.findings.push({
      category: e.catKey,
      message: e.msg,
      field: e.foundField,
      count: e.count,
      detail,
    });
  }

  report.positionsPresent = positions.length;
  if (positions.length > 0) {
    report.startCoarse = coarse(positions[0] as [number, number]);
    report.endCoarse = coarse(positions[positions.length - 1] as [number, number]);
    report.findings.push({
      category: "location",
      message: "record",
      field: "position_lat/long",
      count: positions.length,
      detail: `${positions.length} GPS points; the route starts and ends at real places`,
    });
  }

  const disclosed = new Set(report.findings.map((f) => f.category));
  report.cleanCategories = [...CATEGORY_KEYS, "location"].filter((k) => !disclosed.has(k));
  return report;
}

/** Null the named fields (FIT *invalid*, never zero — contract #4). */
function nullFields(m: Message, names: readonly string[]): [Message, number] {
  const fields = new Map(m.fields);
  let hit = 0;
  for (const name of names) {
    const fv = fields.get(name);
    if (fv !== undefined && fv.value !== null) {
      // Python FieldValue(None, None, fv.units): the developer origin is dropped too.
      const nulled: FieldValue = { value: null, raw: null, units: fv.units, developer: null };
      fields.set(name, nulled);
      hit += 1;
    }
  }
  return hit > 0 ? [{ ...m, fields }, hit] : [m, 0];
}

export interface ScrubOptions {
  /** Drop `user_profile` and identity fields. */
  identity?: boolean;
  /** Null device serial numbers and ANT device ids. Platforms are reported to
   * use `file_id.serial_number` for challenges/badges — keep them if you
   * intend to re-upload. */
  serials?: boolean;
  /** Drop `zones_target` and physiology fields (FTP, max HR, VO2max…). */
  bodyMetrics?: boolean;
  /** Conceal every GPS point within this many metres of the route's **first
   * or last** fix — wherever it occurs in the ride. */
  gpsRadiusM?: number | null;
  /** Remove every coordinate outright. */
  dropAllGps?: boolean;
  /** Parse policy for reading the input. */
  mode?: Mode;
}

/**
 * Remove personal data and write a file that still parses and uploads.
 *
 * Metadata categories are on by default because removing them costs no
 * measurements. Location scrubbing is opt-in and explicit, because it does.
 * Throws `ScrubError` when nothing was selected to remove.
 */
export function scrub(src: Uint8Array, options: ScrubOptions = {}): ScrubResult {
  const identity = options.identity ?? true;
  const serials = options.serials ?? true;
  const bodyMetrics = options.bodyMetrics ?? true;
  const gpsRadiusM = options.gpsRadiusM ?? null;
  const dropAllGps = options.dropAllGps ?? false;
  const mode = options.mode ?? "lenient";

  if (!identity && !serials && !bodyMetrics && !gpsRadiusM && !dropAllGps) {
    throw new ScrubError(
      "SCRUB_NOTHING_SELECTED",
      "scrub() was called with every category disabled",
      {
        suggestion: "enable a category, or pass gps_radius_m= to conceal locations",
      },
    );
  }

  const parsed = parse(src, { mode });
  const enabled: Record<string, boolean> = {
    identity,
    serials,
    body_metrics: bodyMetrics,
  };
  const dropMessages = new Set<string>();
  for (const cat of CATEGORIES) {
    if (enabled[cat.key]) for (const name of cat.messages) dropMessages.add(name);
  }

  let anchors: [number, number][] = [];
  if (gpsRadiusM && !dropAllGps) {
    const fixes: [number, number][] = [];
    for (const m of parsed.messages) {
      if (m.globalNum !== RECORD) continue;
      const p = position(m);
      if (p !== null) fixes.push(p);
    }
    if (fixes.length > 0)
      anchors = [fixes[0] as [number, number], fixes[fixes.length - 1] as [number, number]];
  }

  const kept: Message[] = [];
  const removed: Record<string, number> = {};
  for (const k of [...CATEGORY_KEYS, "location"]) removed[k] = 0;
  let positionsSeen = 0;

  for (const m of parsed.messages) {
    if (dropMessages.has(m.name)) {
      for (const cat of CATEGORIES) {
        if (cat.messages.has(m.name)) removed[cat.key] = (removed[cat.key] as number) + 1;
      }
      continue;
    }
    let msg = m;
    for (const cat of CATEGORIES) {
      if (!enabled[cat.key]) continue;
      if (cat.fieldScope.size > 0 && !cat.fieldScope.has(msg.name)) continue; // see Category.fieldScope
      const [next, hit] = nullFields(msg, cat.fields);
      msg = next;
      removed[cat.key] = (removed[cat.key] as number) + hit;
    }
    if (msg.globalNum === RECORD) {
      const pos = position(msg);
      if (pos !== null) {
        positionsSeen += 1;
        const conceal =
          dropAllGps ||
          (anchors.length > 0 &&
            gpsRadiusM !== null &&
            Math.min(...anchors.map((a) => haversineM(pos, a))) <= gpsRadiusM);
        if (conceal) {
          const [next, hit] = nullFields(msg, POSITION_FIELDS);
          msg = next;
          removed.location = (removed.location as number) + (hit ? 1 : 0);
        }
      }
    } else if ((msg.globalNum === LAP || msg.globalNum === SESSION) && (dropAllGps || gpsRadiusM)) {
      const [next, hit] = nullFields(msg, SUMMARY_POSITION_FIELDS);
      msg = next;
      removed.location = (removed.location as number) + hit;
    }
    kept.push(msg);
  }

  const provenance: ProvenanceEntry[] = [];
  const codes: Record<string, string> = {
    identity: "PII_IDENTITY_REMOVED",
    serials: "PII_SERIALS_REMOVED",
    body_metrics: "PII_BODY_METRICS_REMOVED",
    location: "PII_LOCATION_CONCEALED",
  };
  for (const key of [...CATEGORY_KEYS, "location"]) {
    const count = removed[key] as number;
    if (count) {
      provenance.push({
        code: codes[key] as string,
        action: "dropped",
        scope: "file",
        detail: `removed ${count} ${key.replace(/_/g, " ")} item(s) at the user's request`,
        byteOffset: null,
        data: { category: key, count },
      });
    }
  }

  const warnings: Diagnostic[] = [];
  if (positionsSeen && (removed.location as number) >= positionsSeen) {
    warnings.push({
      code: "SCRUB_ALL_POSITIONS_CONCEALED",
      detail: `every one of the ${positionsSeen} GPS points fell inside the concealment radius; the output has no route at all`,
      scope: "file",
    });
  }

  const data = encodeMessages(kept.map((m) => encodableFromMessage(m)));
  let strictOk = false;
  try {
    parse(data, { mode: "strict" });
    strictOk = true;
  } catch (e) {
    if (!(e instanceof FitError)) throw e;
    strictOk = false;
  }
  const removedOut: Record<string, number> = {};
  for (const [k, v] of Object.entries(removed)) if (v) removedOut[k] = v;
  return {
    data,
    provenance,
    warnings,
    removed: removedOut,
    outputStrictOk: strictOk,
    parseResult: parsed,
  };
}
