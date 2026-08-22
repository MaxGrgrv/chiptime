/**
 * User-directed metadata edits with a validated round-trip.
 *
 * Twin of `python/src/chiptime/edit.py` (F26). chiptime never *infers* intent and
 * never mutates a file on its own — but when the user names an edit explicitly, it
 * is performed, recorded in `provenance[]`, and the result is re-parsed in strict
 * mode to prove the file is still sound. Metadata only: never a measurement.
 */

import { type Mode, parse } from "./api.js";
import { fitTsToIso, fitTsToIsoLocal } from "./decode.js";
import { encodableFromMessage, encodeMessages } from "./encode.js";
import { type Diagnostic, FitError, type ProvenanceEntry } from "./errors.js";
import type { FieldValue, Message } from "./message.js";
import type { Session } from "./model.js";
import { pyFixed, pyFloatStr, pyRound } from "./numeric.js";
import { BASE_TYPES } from "./profile/base-types.js";
import { ENUMS, MESSAGES } from "./profile/index.js";
import type { ParseResult } from "./result.js";

// uint32 range; 0xFFFFFFFF is the invalid sentinel and must never be written
// as a real value (contract #4), so the usable ceiling is one below it.
const TS_MIN = 0;
const TS_MAX = 0xfffffffe;

// The recording device is device_index 0 by convention; other entries are
// sensors (a heart-rate strap did not create the file).
const CREATOR_DEVICE_INDEX = 0;

/** A requested edit cannot be performed; no bytes are written. */
export class EditError extends FitError {}

/** The edited file plus proof of what changed. */
export interface EditResult {
  /** The edited `.fit` bytes — write them to disk as-is. */
  data: Uint8Array;
  /** One entry per edit performed, with before/after values. */
  provenance: ProvenanceEntry[];
  /** Non-fatal observations. chiptime flags; it does not silently fix. */
  warnings: Diagnostic[];
  /** Self-check — the output re-parsed in strict mode. */
  outputStrictOk: boolean;
  /** The parse of the *input*, for inspection. */
  parseResult: ParseResult | null;
}

/** Python's `{v!r}` for the values that appear here: strings quoted, None as None. */
function pyRepr(v: unknown): string {
  if (v === null || v === undefined) return "None";
  if (typeof v === "string") return `'${v}'`;
  if (typeof v === "number" && !Number.isInteger(v)) return pyFloatStr(v);
  return String(v);
}

/** name → value, lowest value wins on aliases (deterministic). */
function reverseEnum(enumName: string): Map<string, number> {
  const out = new Map<string, number>();
  const table = ENUMS[enumName] ?? {};
  const nums = Object.keys(table)
    .map(Number)
    .sort((a, b) => a - b);
  for (const num of nums) {
    const name = (table as Record<number, string>)[num] as string;
    if (!out.has(name)) out.set(name, num);
  }
  return out;
}

function enumRaw(enumName: string, value: string | number): number {
  if (typeof value === "number") {
    return value; // raw numbers pass through: the ecosystem trades in them
  }
  const raw = reverseEnum(enumName).get(String(value));
  if (raw === undefined) {
    throw new EditError("UNKNOWN_ENUM_NAME", `${pyRepr(value)} is not a known ${enumName} value`, {
      suggestion: `pass a raw number instead, or see \`chiptime codes\` for ${enumName}`,
    });
  }
  return raw;
}

function fieldKinds(globalNum: number): Map<string, string> {
  const mdef = MESSAGES[globalNum];
  const out = new Map<string, string>();
  if (mdef) for (const f of Object.values(mdef.fields)) out.set(f.name, f.kind);
  return out;
}

/** Return a copy of `msg` with one field replaced (never mutates input). */
function set(msg: Message, name: string, raw: unknown, value: unknown): Message {
  const old = msg.fields.get(name);
  const fields = new Map(msg.fields);
  const fv: FieldValue = {
    value,
    raw,
    units: old ? old.units : null,
    developer: old ? old.developer : null,
  };
  fields.set(name, fv);
  return { ...msg, fields };
}

function prov(
  code: string,
  scope: string,
  detail: string,
  data: Record<string, unknown>,
): ProvenanceEntry {
  return { code, action: "reinterpreted", scope, detail, byteOffset: null, data };
}

/** Apply sport/sub_sport everywhere the profile declares them, so the file
 * cannot end up internally contradictory. */
function editSport(
  messages: Message[],
  sport: string | number | null,
  subSport: string | number | null,
): [Message[], ProvenanceEntry[], Diagnostic[]] {
  const provs: ProvenanceEntry[] = [];
  const warns: Diagnostic[] = [];
  const sportRaw = sport !== null ? enumRaw("sport", sport) : null;
  const sportName = sportRaw !== null ? (ENUMS.sport?.[sportRaw] ?? sportRaw) : null;
  const subRaw = subSport !== null ? enumRaw("sub_sport", subSport) : null;
  const subName = subRaw !== null ? (ENUMS.sub_sport?.[subRaw] ?? subRaw) : null;

  const out: Message[] = [];
  messages.forEach((m, i) => {
    const kinds = fieldKinds(m.globalNum);
    let msg = m;
    if (sportRaw !== null && kinds.has("sport") && m.fields.has("sport")) {
      const before = m.fields.get("sport")?.value;
      msg = set(msg, "sport", sportRaw, sportName);
      provs.push(
        prov(
          "SPORT_EDITED",
          `message[${i}].${m.name}.sport`,
          `sport ${pyRepr(before)} → ${pyRepr(sportName)} (explicit user edit)`,
          { before: before ?? null, after: sportName },
        ),
      );
      const existingSub = m.fields.get("sub_sport");
      if (
        subRaw === null &&
        existingSub !== undefined &&
        existingSub.value !== null &&
        existingSub.value !== "generic"
      ) {
        warns.push({
          code: "SPORT_PAIR_IMPLAUSIBLE",
          detail:
            `sport changed to ${pyRepr(sportName)} while sub_sport stays ` +
            `${pyRepr(existingSub.value)}; pass sub_sport to change it`,
          scope: `message[${i}].${m.name}`,
        });
      }
    }
    if (subRaw !== null && kinds.has("sub_sport") && m.fields.has("sub_sport")) {
      const before = m.fields.get("sub_sport")?.value;
      msg = set(msg, "sub_sport", subRaw, subName);
      provs.push(
        prov(
          "SPORT_EDITED",
          `message[${i}].${m.name}.sub_sport`,
          `sub_sport ${pyRepr(before)} → ${pyRepr(subName)} (explicit user edit)`,
          { before: before ?? null, after: subName },
        ),
      );
    }
    out.push(msg);
  });
  return [out, provs, warns];
}

/** Rewrite the *recording* device identity only — file_id and the creator
 * entry in device_info. Sensor entries are left alone. */
function editDevice(
  messages: Message[],
  manufacturer: string | number | null,
  product: number | null,
): [Message[], ProvenanceEntry[]] {
  const provs: ProvenanceEntry[] = [];
  const manRaw = manufacturer !== null ? enumRaw("manufacturer", manufacturer) : null;
  const manName = manRaw !== null ? (ENUMS.manufacturer?.[manRaw] ?? manRaw) : null;
  const prodRaw = typeof product === "number" && Number.isInteger(product) ? product : null;
  if (product !== null && prodRaw === null) {
    throw new EditError(
      "UNKNOWN_ENUM_NAME",
      `product ${pyRepr(product)} must be a number (products are vendor-specific)`,
      { suggestion: "pass the numeric product id, e.g. 2480" },
    );
  }

  const out: Message[] = [];
  messages.forEach((m, i) => {
    let msg = m;
    const isFileId = m.name === "file_id";
    const isCreator =
      m.name === "device_info" &&
      m.fields.has("device_index") &&
      m.fields.get("device_index")?.value === CREATOR_DEVICE_INDEX;
    if (!(isFileId || isCreator)) {
      out.push(msg);
      return;
    }
    const edits: [string, number | null, unknown][] = [
      ["manufacturer", manRaw, manName],
      ["product", prodRaw, prodRaw],
    ];
    for (const [fname, raw, val] of edits) {
      if (raw === null || !m.fields.has(fname)) continue;
      const before = m.fields.get(fname)?.value;
      msg = set(msg, fname, raw, val);
      provs.push(
        prov(
          "DEVICE_EDITED",
          `message[${i}].${m.name}.${fname}`,
          `${fname} ${pyRepr(before)} → ${pyRepr(val)} (explicit user edit)`,
          { before: before ?? null, after: val },
        ),
      );
    }
    out.push(msg);
  });
  return [out, provs];
}

/**
 * Shift every profile-typed timestamp, preserving relative spacing.
 *
 * Unknown fields are not shifted: chiptime cannot know an unrecognized field is a
 * timestamp, and guessing would corrupt data (contract #6/#8).
 */
function shiftTime(messages: Message[], seconds: number): [Message[], ProvenanceEntry[]] {
  const out: Message[] = [];
  let shifted = 0;
  for (const m of messages) {
    const kinds = fieldKinds(m.globalNum);
    let msg = m;
    for (const [fname, fv] of m.fields) {
      const kind = kinds.get(fname);
      if (kind !== "date_time" && kind !== "local_date_time") continue;
      if (typeof fv.raw !== "number" || !Number.isInteger(fv.raw)) continue;
      const moved = fv.raw + seconds;
      if (moved < TS_MIN || moved > TS_MAX) {
        throw new EditError(
          "TIME_SHIFT_OUT_OF_RANGE",
          `shifting ${m.name}.${fname} by ${seconds}s would move it to ${moved}, ` +
            `outside the representable FIT range [${TS_MIN}, ${TS_MAX}]`,
          { suggestion: "use a smaller offset; no bytes were written" },
        );
      }
      const iso = kind === "date_time" ? fitTsToIso(moved) : fitTsToIsoLocal(moved);
      msg = set(msg, fname, moved, iso);
      shifted += 1;
    }
    out.push(msg);
  }
  const provs = [
    prov(
      "TIMESTAMPS_SHIFTED",
      "file",
      `shifted ${shifted} timestamp fields by ${seconds}s (relative spacing preserved)`,
      { seconds, fields_shifted: shifted },
    ),
  ];
  return [out, provs];
}

// Fields that must scale together with distance, or the file contradicts
// itself: a speed stream that integrates to a different distance is exactly
// the kind of lie the trim work exists to prevent.
const DISTANCE_FIELDS = ["distance", "total_distance"] as const;
const SPEED_FIELDS = [
  "speed",
  "enhanced_speed",
  "avg_speed",
  "max_speed",
  "enhanced_avg_speed",
  "enhanced_max_speed",
] as const;

/** field name → wire base type code, for bounds checking before we write. */
function wireBaseTypes(msg: Message): Map<string, number> {
  const out = new Map<string, number>();
  const mdef = MESSAGES[msg.globalNum];
  if (mdef === undefined || msg.wire === null) return out;
  const numToName = new Map<number, string>();
  for (const [n, f] of Object.entries(mdef.fields)) numToName.set(Number(n), f.name);
  for (const ws of msg.wire.fields) {
    const name = numToName.get(ws.num);
    if (name !== undefined) out.set(name, ws.baseType);
  }
  return out;
}

/** Would this value survive the wire type it has to be written into? */
function fits(raw: number, baseType: number): boolean {
  const bt = BASE_TYPES[baseType];
  // string/byte carry no numeric invalid (the struct_code=None arm in Python).
  if (bt === undefined || bt.invalid === null) return true;
  if (bt.name.startsWith("float")) return true;
  const invalid = Number(bt.invalid);
  if (bt.name.startsWith("uint") || bt.name.startsWith("enum") || bt.name.startsWith("byte")) {
    return 0 <= raw && raw < invalid; // the invalid pattern is not a usable value
  }
  const limit = invalid; // signed types: invalid is the positive limit
  return -limit <= raw && raw <= limit;
}

/** Scale recorded distance to a user-supplied total, taking speed with it. */
function rescaleDistance(
  messages: Message[],
  targetM: number,
  currentM: number,
): [Message[], ProvenanceEntry[]] {
  if (currentM <= 0) {
    throw new EditError("DISTANCE_NOT_MEASURED", "this file records no distance to rescale", {
      suggestion: "check `chiptime parse` output; no bytes were written",
    });
  }
  const factor = targetM / currentM;
  const out: Message[] = [];
  let touched = 0;
  for (const m of messages) {
    let msg = m;
    const wireTypes = wireBaseTypes(m);
    for (const fname of [...DISTANCE_FIELDS, ...SPEED_FIELDS]) {
      const fv = msg.fields.get(fname);
      if (fv === undefined || typeof fv.raw !== "number") continue;
      const scaledRaw = Number.isInteger(fv.raw) ? pyRound(fv.raw * factor) : fv.raw * factor;
      const baseType = wireTypes.get(fname);
      if (baseType !== undefined && !fits(scaledRaw, baseType)) {
        throw new EditError(
          "DISTANCE_SCALE_OUT_OF_RANGE",
          `scaling by ${pyFixed(factor, 3)} would push ${m.name}.${fname} to ` +
            `${Number.isInteger(scaledRaw) ? scaledRaw : pyFloatStr(scaledRaw)}, which does not fit its wire type`,
          {
            suggestion:
              "the requested distance is too far from the recorded one; no bytes were written",
          },
        );
      }
      const value = typeof fv.value === "number" ? fv.value * factor : fv.value;
      msg = set(msg, fname, scaledRaw, value);
      touched += 1;
    }
    out.push(msg);
  }
  const provs = [
    prov(
      "DISTANCE_RESCALED",
      "file",
      `distance rescaled ${pyFixed(currentM, 0)}m → ${pyFixed(targetM, 0)}m ` +
        `(factor ${pyFixed(factor, 4)}); speed scaled identically across ${touched} field(s)`,
      { factor, from_m: currentM, to_m: targetM, fields: touched },
    ),
  ];
  return [out, provs];
}

export interface EditOptions {
  /** New sport, by profile name (`"running"`) or raw number. */
  sport?: string | number | null;
  /** New sub-sport; never inferred from `sport`. */
  subSport?: string | number | null;
  /** New recording-device manufacturer, name or number. */
  manufacturer?: string | number | null;
  /** New product id (numeric — products are vendor-specific). */
  product?: number | null;
  /** Signed seconds added to every profile-typed timestamp. */
  timeShiftS?: number | null;
  /** Set the activity's true distance (treadmill calibration). */
  totalDistanceM?: number | null;
  /** Parse policy for reading the input. `strict` refuses to edit a file that
   * does not parse strictly; use `repair` first if it is not. */
  mode?: Mode;
}

/**
 * Change what a file *says about itself*, then prove it still parses.
 *
 * Only the named edits are applied; every other message, field, developer field,
 * and unknown value round-trips untouched. Each edit is recorded in
 * `provenance[]`, and the output is re-parsed in strict mode (`outputStrictOk`).
 *
 * Throws `EditError` when no edit was requested, an enum name is unknown, or a
 * time shift would leave the representable range. No bytes are written in any of
 * these cases.
 */
export function edit(src: Uint8Array, options: EditOptions = {}): EditResult {
  const sport = options.sport ?? null;
  const subSport = options.subSport ?? null;
  const manufacturer = options.manufacturer ?? null;
  const product = options.product ?? null;
  const timeShiftS = options.timeShiftS ?? null;
  const totalDistanceM = options.totalDistanceM ?? null;
  const mode = options.mode ?? "lenient";

  if (
    sport === null &&
    subSport === null &&
    manufacturer === null &&
    product === null &&
    timeShiftS === null &&
    totalDistanceM === null
  ) {
    throw new EditError("NO_EDIT_REQUESTED", "edit() was called without any edit to perform", {
      suggestion:
        "pass sport=, sub_sport=, manufacturer=, product=, time_shift_s=, or total_distance_m=",
    });
  }

  const parsed = parse(src, { mode });
  let messages = [...parsed.messages];
  const provenance: ProvenanceEntry[] = [];
  const warnings: Diagnostic[] = [];

  if (sport !== null || subSport !== null) {
    const [msgs, provs, warns] = editSport(messages, sport, subSport);
    messages = msgs;
    provenance.push(...provs);
    warnings.push(...warns);
  }
  if (manufacturer !== null || product !== null) {
    const [msgs, provs] = editDevice(messages, manufacturer, product);
    messages = msgs;
    provenance.push(...provs);
  }
  if (timeShiftS !== null && timeShiftS !== 0) {
    const [msgs, provs] = shiftTime(messages, timeShiftS);
    messages = msgs;
    provenance.push(...provs);
  }
  if (totalDistanceM !== null) {
    const activity = parsed.activity as { sessions: Session[] } | null;
    let current: number | null = null;
    if (activity !== null && activity.sessions !== undefined && activity.sessions.length > 0) {
      const session = activity.sessions[0] as Session;
      // Python `or`: a zero derived distance falls through to the declared one.
      current =
        session.derived.distanceM ||
        (session.declared !== null ? session.declared.distanceM : null);
    }
    const [msgs, provs] = rescaleDistance(messages, totalDistanceM, current || 0.0);
    messages = msgs;
    provenance.push(...provs);
  }

  const data = encodeMessages(messages.map((m) => encodableFromMessage(m)));
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
    warnings,
    outputStrictOk: strictOk,
    parseResult: parsed,
  };
}
