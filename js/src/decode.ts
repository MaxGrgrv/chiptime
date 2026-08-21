/**
 * Frames to messages: base types, sentinels, scale/offset, enums, strings,
 * timestamps, developer fields and component expansion.
 *
 * Twin of `python/src/chiptime/decode.py`. Two hazards shape this port and are
 * flagged at each site:
 *
 *   - **JavaScript bitwise operators are 32-bit signed.** FIT `date_time` is a
 *     `uint32` whose values exceed 2^31, so `anchor & ~0x1f` silently goes negative
 *     where Python's arbitrary-precision `&` does not. Every masking site here uses
 *     modulo arithmetic instead.
 *   - **`%` is not Python's `%`.** JavaScript's remainder takes the sign of the
 *     dividend; Python's takes the divisor. The rollover math depends on the
 *     Python behavior, so it goes through `floorMod`.
 */

import { type Defect, type Diagnostic, type ProvenanceEntry, defect } from "./errors.js";
import type { DataFrame, DefinitionFrame } from "./frames.js";
import type { DevFieldOrigin, FieldValue, Message } from "./message.js";
import { floorDiv } from "./numeric.js";
import type { FieldDef, MessageDef } from "./profile/core.js";
import { BASE_TYPES, type BaseType, ENUMS, MESSAGES, isInvalid } from "./profile/index.js";
import { lookup as vendorLookup } from "./profile/registry.js";

/**
 * `TextDecoder` is universal (Node >= 11, browsers, Deno, Bun) but absent from
 * `lib: ["ES2022"]`. Declared minimally rather than by pulling in the DOM lib, which
 * would let genuinely browser-only APIs compile by accident.
 *
 * Its replacement behavior was verified equal to CPython's `errors="replace"` across
 * ten adversarial sequences, including the maximal-subpart cases where the two
 * specifications could have disagreed about how many U+FFFD to emit.
 */
declare class TextDecoder {
  constructor(label?: string, options?: { fatal?: boolean });
  decode(input?: Uint8Array): string;
}
const UTF8 = new TextDecoder("utf-8");

export const FIT_EPOCH_UNIX = 631065600; // 1989-12-31T00:00:00Z (taxonomy #36)
export const RELATIVE_TS_CEILING = 0x10000000; // below this, date_time is device-relative

/** Python's `%`: the result takes the sign of the divisor. */
function floorMod(a: number, b: number): number {
  return a - b * floorDiv(a, b);
}

/**
 * Unix seconds to (y, m, d, hh, mm, ss) UTC. Hinnant's civil_from_days, the same
 * integer algorithm `decode.py` uses -- and the reason `Date` never appears here
 * (ADR-0009 section 5): `toISOString()` always emits milliseconds, which the Python
 * formatter does not.
 */
export function civilFromUnix(unix: number): [number, number, number, number, number, number] {
  const days = floorDiv(unix, 86400);
  let rem = unix - days * 86400;
  const hh = floorDiv(rem, 3600);
  rem -= hh * 3600;
  const mm = floorDiv(rem, 60);
  const ss = rem - mm * 60;
  const z = days + 719468;
  const era = floorDiv(z >= 0 ? z : z - 146096, 146097);
  const doe = z - era * 146097;
  const yoe = floorDiv(
    doe - floorDiv(doe, 1460) + floorDiv(doe, 36524) - floorDiv(doe, 146096),
    365,
  );
  const y = yoe + era * 400;
  const doy = doe - (365 * yoe + floorDiv(yoe, 4) - floorDiv(yoe, 100));
  const mp = floorDiv(5 * doy + 2, 153);
  const d = doy - floorDiv(153 * mp + 2, 5) + 1;
  const m = mp < 10 ? mp + 3 : mp - 9;
  return [y + (m <= 2 ? 1 : 0), m, d, hh, mm, ss];
}

function pad(n: number, width: number): string {
  return String(n).padStart(width, "0");
}

export function fitTsToIso(fitSeconds: number): string {
  const [y, m, d, hh, mm, ss] = civilFromUnix(FIT_EPOCH_UNIX + fitSeconds);
  return `${pad(y, 4)}-${pad(m, 2)}-${pad(d, 2)}T${pad(hh, 2)}:${pad(mm, 2)}:${pad(ss, 2)}Z`;
}

export function fitTsToIsoLocal(fitSeconds: number): string {
  const [y, m, d, hh, mm, ss] = civilFromUnix(FIT_EPOCH_UNIX + fitSeconds);
  return `${pad(y, 4)}-${pad(m, 2)}-${pad(d, 2)}T${pad(hh, 2)}:${pad(mm, 2)}:${pad(ss, 2)}`;
}

const NAME_RE = /[^a-z0-9]+/g;

export function sanitizeFieldName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(NAME_RE, "_")
    .replace(/^_+|_+$/g, "");
}

export interface DecodeOutput {
  messages: Message[];
  diagnostics: Diagnostic[];
  provenance: ProvenanceEntry[];
  defects: Defect[];
}

interface FieldPlan {
  num: number;
  baseTypeByte: number;
  name: string;
  fdef: FieldDef | undefined;
  bt: BaseType | undefined;
  count: number;
  size: number;
  /** Signed-adjusted sentinel; `null` for floats and n/a. */
  invalid: number | bigint | null;
  isFloat: boolean;
  isTs253: boolean;
  /** Scalar, known base type, plain number without enum/date semantics. */
  fastNumber: boolean;
}

interface DevDesc {
  name: string | null;
  baseTypeId: number | null;
  scale: number | null;
  offset: number | null;
  units: string | null;
}

const SIGNED_INVALID: Readonly<Record<string, number | bigint>> = {
  sint8: 0x7f,
  sint16: 0x7fff,
  sint32: 0x7fffffff,
  sint64: 0x7fffffffffffffffn,
};

function allBytes(raw: Uint8Array, value: number): boolean {
  for (const b of raw) if (b !== value) return false;
  return true;
}

function anyByteNot(raw: Uint8Array, value: number): boolean {
  for (const b of raw) if (b !== value) return true;
  return false;
}

function toHex(raw: Uint8Array): string {
  let out = "";
  for (const b of raw) out += b.toString(16).padStart(2, "0");
  return out;
}

/** Read `count` elements of `bt` from `raw` at the definition's endianness. */
function readElements(
  raw: Uint8Array,
  bt: BaseType,
  count: number,
  big: boolean,
): (number | bigint)[] {
  const view = new DataView(raw.buffer, raw.byteOffset, raw.byteLength);
  const out: (number | bigint)[] = [];
  const little = !big;
  for (let i = 0; i < count; i++) {
    const at = i * bt.size;
    switch (bt.accessor) {
      case "getInt8":
        out.push(view.getInt8(at));
        break;
      case "getUint8":
        out.push(view.getUint8(at));
        break;
      case "getInt16":
        out.push(view.getInt16(at, little));
        break;
      case "getUint16":
        out.push(view.getUint16(at, little));
        break;
      case "getInt32":
        out.push(view.getInt32(at, little));
        break;
      case "getUint32":
        out.push(view.getUint32(at, little));
        break;
      case "getFloat32":
        out.push(view.getFloat32(at, little));
        break;
      case "getFloat64":
        out.push(view.getFloat64(at, little));
        break;
      case "getBigInt64":
        out.push(view.getBigInt64(at, little));
        break;
      case "getBigUint64":
        out.push(view.getBigUint64(at, little));
        break;
      default:
        break;
    }
  }
  return out;
}

/**
 * Convert a raw wire value to a `number` for scale/offset arithmetic.
 *
 * Python's `raw / scale` accepts any int; TypeScript throws on mixed bigint/number.
 * Beyond 2^53 this conversion is lossy — which is exactly why the shaping layer
 * serializes such values as decimal strings (ADR-0002 section 2). The *raw* is kept
 * intact on the FieldValue either way, so nothing is lost that the output needs.
 */
function toNumber(raw: number | bigint): number {
  return typeof raw === "bigint" ? Number(raw) : raw;
}

function fv(
  value: unknown,
  raw: unknown,
  units: string | null = null,
  developer: DevFieldOrigin | null = null,
): FieldValue {
  return { value, raw, units, developer };
}

export class Decoder {
  lastTimestamp: number | null = null;
  fileIdCreated: number | null = null;
  readonly out: DecodeOutput = { messages: [], diagnostics: [], provenance: [], defects: [] };

  private diagSeen = new Set<string>();
  /** key -> [count, firstOffset, defOffset, fieldNum, why] — the tuple survives for sorting. */
  private salvageAgg = new Map<string, [number, number, number, number, string]>();
  private anchorSynthesized = false;
  private anchorMissingReported = false;
  private hrTs1024: number | null = null;
  private csdTotal16ths = 0;
  private csdLast12: number | null = null;
  private accPowerWraps = 0;
  private accPowerLast: number | null = null;
  private plans = new Map<DefinitionFrame, FieldPlan[]>();
  private devApps = new Map<number, [string | null, string | null]>();
  private devDescs = new Map<string, DevDesc>();
  private unresolvedDev: [number, string, number, number, Uint8Array, boolean][] = [];

  decode(frame: DataFrame): Message {
    const gnum = frame.definition.globalNum;
    const mdef = MESSAGES[gnum];
    const name = mdef ? mdef.name : `unknown_${gnum}`;
    const fields = new Map<string, FieldValue>();
    let pos = 0;
    const payload = frame.payload;
    const big = frame.definition.bigEndian;

    let plan = this.plans.get(frame.definition);
    if (plan === undefined) {
      plan = this.buildPlan(frame.definition, mdef);
      this.plans.set(frame.definition, plan);
    }

    for (const fp of plan) {
      const rawBytes = payload.subarray(pos, pos + fp.size);
      pos += fp.size;
      let fname = fp.name;
      const bt = fp.bt;

      if (
        bt !== undefined &&
        bt.accessor !== null &&
        fp.count === 1 &&
        rawBytes.length >= bt.size
      ) {
        const raw0 = readElements(rawBytes, bt, 1, big)[0] as number | bigint;
        if (fp.fastNumber) {
          // Hottest path: plain scalar integer.
          if (raw0 === fp.invalid) {
            fields.set(fname, fv(null, raw0, fp.fdef?.units ?? null));
          } else {
            const fdef = fp.fdef;
            let v: unknown = raw0;
            if (fdef !== undefined && fdef.scale !== 1.0) {
              let scaled = toNumber(raw0) / fdef.scale;
              if (fdef.offset) scaled = scaled - fdef.offset;
              v = scaled;
            } else if (fdef?.offset) {
              v = toNumber(raw0) - fdef.offset;
            }
            fields.set(fname, fv(v, raw0, fdef?.units ?? null));
          }
          continue;
        }
        if (fp.isFloat && allBytes(rawBytes, 0xff)) {
          // Exact invalid pattern = normal absence, no warning (muktihari#39).
          fields.set(fname, fv(null, raw0, fp.fdef?.units ?? null));
          continue;
        }
        let value = this.element(raw0, bt, fp.fdef, name, fname);
        if (fp.isTs253 && typeof raw0 === "number") {
          if (!isInvalid(bt, raw0) && raw0 >= RELATIVE_TS_CEILING) this.lastTimestamp = raw0;
          if (fp.fdef === undefined) {
            fname = "timestamp";
            value = this.dateTime(raw0, name, fname);
          }
        }
        fields.set(fname, fv(value, raw0, fp.fdef?.units ?? null));
        continue;
      }

      if (fp.num === 253 && fp.size === 4 && (fp.bt === undefined || fp.bt.size === 1)) {
        // fitdecode#33 (Xiaomi pipeline): timestamp declared as byte[4].
        let tsRaw = 0;
        for (let i = 0; i < 4; i++) {
          const b = rawBytes[big ? i : 3 - i] ?? 0;
          tsRaw = tsRaw * 256 + b;
        }
        this.diag(
          "TIMESTAMP_DECLARED_AS_BYTES",
          `${name}: field 253 declared as 4 single-byte units; reassembled as uint32 (Xiaomi-pipeline class)`,
          name,
        );
        if (tsRaw >= RELATIVE_TS_CEILING) this.lastTimestamp = tsRaw;
        fields.set("timestamp", fv(this.dateTime(tsRaw, name, "timestamp"), tsRaw, "datetime"));
        continue;
      }
      fields.set(fname, this.slowField(fp, rawBytes, name, big, frame));
    }

    for (const devSpec of frame.definition.devFields) {
      const rawDev = payload.subarray(pos, pos + devSpec.size);
      pos += devSpec.size;
      const idx = devSpec.devDataIndex;
      const num2 = devSpec.num;
      const resolved = this.resolveDev(idx, num2, rawDev, fields, big);
      if (resolved === null) {
        // Missing/null metadata (taxonomy #22a/b): synthesize a name, keep the data,
        // warn once, allow late back-fill.
        const pname = `dev_${idx}_${num2}`;
        const [appId, vendor] = this.devApps.get(idx) ?? [null, null];
        this.diag(
          "DEV_FIELD_NAME_SYNTHESIZED",
          `developer field ${idx}/${num2} in ${name} has no usable field_description; named ${pname}, raw bytes kept`,
          `dev.${idx}.${num2}`,
        );
        fields.set(
          pname,
          fv(null, rawDev, null, {
            developerDataIndex: idx,
            fieldDefinitionNumber: num2,
            applicationId: appId,
            vendor,
            canonicalName: null,
          }),
        );
        this.unresolvedDev.push([this.out.messages.length, pname, idx, num2, rawDev, big]);
      } else {
        fields.set(resolved[0], resolved[1]);
      }
    }

    if (gnum === 20) this.expandRecordComponents(fields, frame);
    else if (gnum === 21) this.resolveEventSubfield(fields);
    else if (gnum === 132) this.expandHr(fields, frame);
    if (fields.has("timestamp_16")) this.mergeTimestamp16(fields, frame);
    if (fields.has("left_right_balance") || fields.has("left_right_balance_100")) {
      this.decodeBalance(fields);
    }
    if ((gnum === 0 || gnum === 23) && fields.has("product")) this.resolveProduct(fields);

    if (frame.timeOffset !== null) this.compressedTimestamp(frame, fields, name);

    const msg: Message = {
      globalNum: gnum,
      name,
      localId: frame.localId,
      byteOffset: frame.offset,
      fields,
      wire: frame.definition,
    };

    if (gnum === 0) {
      // file_id: remember creation time as anchor of last resort.
      const created = fields.get("time_created")?.raw;
      if (typeof created === "number" && created >= RELATIVE_TS_CEILING) {
        this.fileIdCreated = created;
      }
    } else if (gnum === 207) {
      // developer_data_id (taxonomy #22)
      const didx = fields.get("developer_data_index")?.value;
      if (typeof didx === "number") {
        if (this.devApps.has(didx)) {
          this.diag(
            "DEV_INDEX_REDEFINED",
            `developer_data_index ${didx} redefined by another application mid-file; later definitions apply forward`,
            `dev.${didx}`,
          );
        }
        const appRaw = fields.get("application_id")?.raw;
        const appHex = appRaw instanceof Uint8Array ? toHex(appRaw) : null;
        const manu = fields.get("manufacturer_id")?.value;
        this.devApps.set(didx, [appHex, typeof manu === "string" ? manu : null]);
      }
    } else if (gnum === 206) {
      // field_description
      const didx = fields.get("developer_data_index")?.value;
      const fnum = fields.get("field_definition_number")?.value;
      if (typeof didx === "number" && typeof fnum === "number") {
        if (!this.devApps.has(didx)) {
          this.diag(
            "DEV_DATA_ID_MISSING",
            `field_description for developer_data_index ${didx} arrived without a developer_data_id message (spec violation; tolerated)`,
            `dev.${didx}`,
          );
        }
        const nameV = fields.get("field_name")?.value;
        const btV = fields.get("fit_base_type_id")?.value;
        const scV = fields.get("scale")?.value;
        const ofV = fields.get("offset")?.value;
        const unV = fields.get("units")?.value;
        this.devDescs.set(`${didx}:${fnum}`, {
          name: typeof nameV === "string" ? nameV : null,
          baseTypeId: typeof btV === "number" ? btV : null,
          scale: typeof scV === "number" ? scV : null,
          offset: typeof ofV === "number" ? ofV : null,
          units: typeof unV === "string" ? unV : null,
        });
      }
    }
    this.out.messages.push(msg);
    return msg;
  }

  finish(): DecodeOutput {
    let resolvedLate = 0;
    for (const [mi, pname, idx, num, rawDev, big] of this.unresolvedDev) {
      const msg = this.out.messages[mi];
      if (msg === undefined) continue;
      const existing = new Map(msg.fields);
      existing.delete(pname);
      const resolved = this.resolveDev(idx, num, rawDev, existing, big);
      if (resolved === null) continue;
      existing.set(resolved[0], resolved[1]);
      this.out.messages[mi] = { ...msg, fields: existing };
      resolvedLate += 1;
    }
    if (resolvedLate) {
      this.out.provenance.push({
        code: "DEV_FIELD_RESOLVED_LATE",
        action: "reinterpreted",
        scope: "stream",
        detail: `${resolvedLate} developer field value(s) re-resolved after their field_description arrived later in the file`,
        byteOffset: null,
        data: { count: resolvedLate },
      });
    }
    // Python sorts the aggregation by its (defOffset, fieldNum, why) TUPLE. A string
    // key would sort lexicographically and put definition@100 before definition@20,
    // so the tuple is reconstructed and compared component by component.
    const entries = [...this.salvageAgg.values()].sort((a, b) => {
      if (a[2] !== b[2]) return a[2] - b[2];
      if (a[3] !== b[3]) return a[3] - b[3];
      return a[4] < b[4] ? -1 : a[4] > b[4] ? 1 : 0;
    });
    for (const [n, first, defOffset, fnum, why] of entries) {
      this.out.provenance.push({
        code: "FIELD_RAW_SALVAGED",
        action: "reinterpreted",
        scope: `definition@${defOffset}.field_${fnum}`,
        detail: `${why}; raw bytes kept for ${n} message(s)`,
        byteOffset: first,
        data: { count: n, definition_offset: defOffset, field_num: fnum },
      });
    }
    return this.out;
  }

  // ── internals ─────────────────────────────────────────────────────────

  private element(
    raw: number | bigint,
    bt: BaseType,
    fdef: FieldDef | undefined,
    mname: string,
    fname: string,
  ): unknown {
    if (bt.name === "float32" || bt.name === "float64") {
      if (typeof raw === "number" && !Number.isFinite(raw)) {
        // Sentinel pattern is itself a NaN; either way the value is absent (#35).
        this.diag(
          "NONFINITE_FLOAT_NULLED",
          `non-finite float in ${mname}.${fname}; treated as absent`,
          `${mname}.${fname}`,
        );
        return null;
      }
    } else if (isInvalid(bt, raw)) {
      return null; // sentinel -> absent (taxonomy #26), BEFORE scaling
    }

    if (fdef === undefined) return raw;

    if (fdef.kind.startsWith("enum:")) {
      const mapping = ENUMS[fdef.kind.slice(5)] ?? {};
      const key = Number(raw);
      const mapped = mapping[key];
      return mapped !== undefined ? mapped : raw; // unknown enum -> raw int (taxonomy #24)
    }
    if (fdef.kind === "date_time") return this.dateTime(Number(raw), mname, fname);
    if (fdef.kind === "local_date_time") {
      const n = Number(raw);
      if (n < RELATIVE_TS_CEILING) {
        this.diag(
          "RELATIVE_TIMESTAMP",
          `${mname}.${fname} is below 0x10000000 (device-relative); value kept raw`,
          `${mname}.${fname}`,
        );
        return null;
      }
      return fitTsToIsoLocal(n);
    }

    let value: number | bigint = raw;
    if (fdef.scale !== 1.0) value = toNumber(value) / fdef.scale;
    if (fdef.offset) value = toNumber(value) - fdef.offset;
    return value;
  }

  private dateTime(raw: number, mname: string, fname: string): string | null {
    if (raw < RELATIVE_TS_CEILING) {
      this.diag(
        "RELATIVE_TIMESTAMP",
        `${mname}.${fname} is below 0x10000000 (device-relative); value kept raw`,
        `${mname}.${fname}`,
      );
      return null;
    }
    return fitTsToIso(raw);
  }

  private decodeString(raw: Uint8Array, mname: string, fname: string): FieldValue {
    const segments: string[] = [];
    let pos = 0;
    let replaced = false;
    while (pos < raw.length) {
      const nul = raw.indexOf(0, pos);
      if (nul < 0) {
        if (segments.length === 0) {
          // Single unterminated string (fitparse#75).
          this.diag(
            "STRING_UNTERMINATED",
            `${mname}.${fname} has no NUL terminator; whole buffer used`,
            `${mname}.${fname}`,
          );
          const text = UTF8.decode(raw.subarray(pos));
          replaced = replaced || text.includes("�");
          segments.push(text);
        }
        break; // terminated segments exist: tail is padding junk
      }
      if (nul === pos) break; // empty segment = end of array
      const text = UTF8.decode(raw.subarray(pos, nul));
      if (text.includes("�") && segments.length > 0) break; // padding junk (#436)
      replaced = replaced || text.includes("�");
      segments.push(text);
      pos = nul + 1;
    }
    if (replaced) {
      this.diag(
        "STRING_DECODE_REPLACED",
        `${mname}.${fname} contained invalid UTF-8; replacement characters used`,
        `${mname}.${fname}`,
      );
    }
    const kept = segments.filter((t) => t !== "");
    if (kept.length === 0) return fv(null, raw);
    if (kept.length === 1) return fv(kept[0], raw);
    return fv(kept, raw);
  }

  private compressedTimestamp(
    frame: DataFrame,
    fields: Map<string, FieldValue>,
    mname: string,
  ): void {
    const toff = frame.timeOffset;
    if (toff === null) return;
    if (fields.has("timestamp")) {
      this.diag(
        "COMPRESSED_AND_EXPLICIT_TIMESTAMP",
        `${mname} carries both a compressed header and field 253; explicit value kept`,
        mname,
      );
      return;
    }
    let anchor = this.lastTimestamp;
    if (anchor === null && this.fileIdCreated !== null) {
      anchor = this.fileIdCreated;
      if (!this.anchorSynthesized) {
        this.anchorSynthesized = true;
        this.out.provenance.push({
          code: "TIMESTAMP_ANCHOR_FROM_FILE_ID",
          action: "synthesized",
          scope: "stream",
          detail:
            "compressed timestamps appeared before any full timestamp; anchored from file_id.time_created",
          byteOffset: frame.offset,
          data: {},
        });
      }
    }
    if (anchor === null) {
      if (!this.anchorMissingReported) {
        this.anchorMissingReported = true;
        this.out.defects.push(
          defect(
            "FIT_MISSING_TIMESTAMP_ANCHOR",
            "compressed-timestamp record appeared before any full timestamp and file_id has no usable time_created",
            frame.offset,
            "data",
          ),
        );
      }
      return;
    }
    // `anchor & ~0x1f` in Python; here modulo, because a uint32 date_time exceeds
    // 2^31 and JavaScript's `&` would truncate it to a negative int32.
    const low5 = anchor % 32;
    const ts = anchor - low5 + toff + (toff < low5 ? 0x20 : 0);
    this.lastTimestamp = ts;
    fields.set("timestamp", fv(fitTsToIso(ts), ts, "datetime"));
  }

  private buildPlan(definition: DefinitionFrame, mdef: MessageDef | undefined): FieldPlan[] {
    const plan: FieldPlan[] = [];
    for (const spec of definition.fields) {
      const fdef = mdef ? mdef.fields[spec.num] : undefined;
      const fname = fdef ? fdef.name : `field_${spec.num}`;
      const bt = BASE_TYPES[spec.baseType];
      let count = 0;
      let invalid: number | bigint | null = null;
      let isFloat = false;
      let fast = false;
      if (bt !== undefined && bt.accessor !== null) {
        count = Math.floor(spec.size / bt.size);
        isFloat = bt.name === "float32" || bt.name === "float64";
        if (!isFloat) invalid = SIGNED_INVALID[bt.name] ?? bt.invalid;
        fast =
          count === 1 &&
          spec.size === bt.size &&
          spec.num !== 253 &&
          !isFloat && // floats need element()'s non-finite diagnostics
          (fdef === undefined || fdef.kind === "number");
      }
      plan.push({
        num: spec.num,
        baseTypeByte: spec.baseType,
        name: fname,
        fdef,
        bt,
        count,
        size: spec.size,
        invalid,
        isFloat,
        isTs253: spec.num === 253 && bt !== undefined && bt.name === "uint32",
        fastNumber: fast,
      });
    }
    return plan;
  }

  private slowField(
    fp: FieldPlan,
    rawBytes: Uint8Array,
    mname: string,
    big: boolean,
    frame: DataFrame,
  ): FieldValue {
    const bt = fp.bt;
    if (bt === undefined) {
      // Unknown base type (taxonomy #25).
      this.salvage(
        frame.definition.offset,
        fp.num,
        "unknown base type",
        frame.offset,
        "FIT_BASE_TYPE_INVALID",
        `field ${fp.num} declares unknown base type 0x${fp.baseTypeByte.toString(16).toUpperCase().padStart(2, "0")}`,
      );
      return fv(null, rawBytes);
    }
    if (bt.name === "string") return this.decodeString(rawBytes, mname, fp.name);
    if (bt.name === "byte") {
      return fv(allBytes(rawBytes, 0xff) ? null : rawBytes, rawBytes);
    }
    if (fp.count === 0) {
      this.salvage(
        frame.definition.offset,
        fp.num,
        `size ${fp.size} smaller than base type ${bt.name}`,
        frame.offset,
      );
      return fv(null, rawBytes);
    }
    if (fp.size % bt.size) {
      this.salvage(
        frame.definition.offset,
        fp.num,
        `size ${fp.size} not a multiple of ${bt.name} (${bt.size}); trailing bytes kept raw`,
        frame.offset,
        "FIT_FIELD_SIZE_INVALID",
        `field ${fp.num} size ${fp.size} not a multiple of ${bt.name} size ${bt.size}`,
      );
    }
    const raws = readElements(rawBytes, bt, fp.count, big);
    let values: unknown[];
    if (fp.isFloat) {
      values = raws.map((r, i) =>
        allBytes(rawBytes.subarray(i * bt.size, (i + 1) * bt.size), 0xff)
          ? null
          : this.element(r, bt, fp.fdef, mname, fp.name),
      );
    } else {
      values = raws.map((r) => this.element(r, bt, fp.fdef, mname, fp.name));
    }
    const rawOut: unknown = fp.count > 1 ? raws : raws[0];
    let value: unknown;
    if (fp.count > 1) {
      while (values.length > 0 && values[values.length - 1] === null) values.pop(); // #34
      value = values.length > 0 ? values : null;
    } else {
      value = values[0];
    }
    return fv(value, rawOut, fp.fdef?.units ?? null);
  }

  private resolveDev(
    idx: number,
    num: number,
    raw: Uint8Array,
    existing: Map<string, FieldValue>,
    big: boolean,
  ): [string, FieldValue] | null {
    const desc = this.devDescs.get(`${idx}:${num}`);
    if (desc === undefined || !desc.name) return null;
    const base = sanitizeFieldName(desc.name);
    if (!base) return null;
    const [appId, vendor] = this.devApps.get(idx) ?? [null, null];
    const bt = desc.baseTypeId !== null ? BASE_TYPES[desc.baseTypeId] : undefined;
    let value: unknown;
    let wire: unknown;
    if (bt === undefined) {
      value = anyByteNot(raw, 0xff) ? raw : null;
      wire = raw;
    } else if (bt.name === "string") {
      const nul = raw.indexOf(0);
      const text = UTF8.decode(nul < 0 ? raw : raw.subarray(0, nul));
      value = text || null;
      wire = raw;
    } else if (bt.accessor === null) {
      value = anyByteNot(raw, 0xff) ? raw : null;
      wire = raw;
    } else if (raw.length % bt.size || raw.length === 0) {
      value = null;
      wire = raw;
    } else {
      const count = raw.length / bt.size;
      const raws = readElements(raw, bt, count, big);
      const vals: unknown[] = [];
      for (const r of raws) {
        const nonfinite = typeof r === "number" && !Number.isFinite(r);
        if (nonfinite || isInvalid(bt, r)) {
          vals.push(null);
        } else {
          let v: number | bigint = r;
          if (desc.scale !== null && desc.scale !== 0.0 && desc.scale !== 1.0) {
            v = toNumber(v) / desc.scale;
          }
          if (desc.offset) v = toNumber(v) - desc.offset;
          vals.push(v);
        }
      }
      if (count === 1) {
        value = vals[0];
        wire = raws[0];
      } else {
        while (vals.length > 0 && vals[vals.length - 1] === null) vals.pop();
        value = vals.length > 0 ? vals : null;
        wire = raws;
      }
    }
    const match = vendorLookup(vendor, desc.name);
    const units = desc.units ?? match?.units ?? null;
    const fname = existing.has(base) ? `${base}_${idx}_${num}` : base;
    const origin: DevFieldOrigin = {
      developerDataIndex: idx,
      fieldDefinitionNumber: num,
      applicationId: appId,
      vendor,
      canonicalName: match ? match.canonicalName : null,
    };
    return [fname, fv(value, wire, units, origin)];
  }

  private expandRecordComponents(fields: Map<string, FieldValue>, frame: DataFrame): void {
    const csd = fields.get("compressed_speed_distance");
    if (csd !== undefined && csd.raw instanceof Uint8Array && csd.raw.length === 3) {
      const b0 = csd.raw[0] as number;
      const b1 = csd.raw[1] as number;
      const b2 = csd.raw[2] as number;
      const speedRaw = b0 | ((b1 & 0x0f) << 8);
      const dist12 = (b1 >> 4) | (b2 << 4);
      if (speedRaw !== 0xfff || dist12 !== 0xfff) {
        if (this.csdLast12 === null) this.csdLast12 = dist12;
        // Python's `%` is non-negative; JavaScript's takes the dividend's sign.
        const delta = floorMod(dist12 - this.csdLast12, 4096);
        this.csdTotal16ths += delta;
        this.csdLast12 = dist12;
        if (!fields.has("speed") && speedRaw !== 0xfff) {
          fields.set("speed", fv(speedRaw / 100.0, speedRaw, "m/s"));
        }
        if (!fields.has("distance")) {
          fields.set("distance", fv(this.csdTotal16ths / 16.0, this.csdTotal16ths, "m"));
        }
        this.salvage(
          frame.definition.offset,
          8,
          "compressed_speed_distance expanded",
          frame.offset,
        );
      }
    }
    const acc = fields.get("accumulated_power");
    if (acc !== undefined && typeof acc.raw === "number") {
      if (this.accPowerLast !== null && acc.raw < this.accPowerLast) {
        this.accPowerWraps += 1;
        this.salvage(
          frame.definition.offset,
          29,
          "accumulated_power wrapped its uint32; unwrapped",
          frame.offset,
        );
      }
      this.accPowerLast = acc.raw;
      if (this.accPowerWraps) {
        fields.set(
          "accumulated_power",
          fv(acc.raw + this.accPowerWraps * 2 ** 32, acc.raw, "watts"),
        );
      }
    }
  }

  private mergeTimestamp16(fields: Map<string, FieldValue>, frame: DataFrame): void {
    const t16 = fields.get("timestamp_16")?.raw;
    if (typeof t16 !== "number" || t16 === 0xffff || this.lastTimestamp === null) return;
    // Modulo rather than `& 0xffff`: last can exceed 2^31 as a uint32 date_time.
    const full = this.lastTimestamp + floorMod(t16 - (this.lastTimestamp % 65536), 65536);
    this.lastTimestamp = full;
    if (!fields.has("timestamp")) {
      fields.set("timestamp", fv(fitTsToIso(full), full, "datetime"));
      this.salvage(
        frame.definition.offset,
        254,
        "timestamp_16 merged onto rolling timestamp",
        frame.offset,
      );
    }
  }

  private expandHr(fields: Map<string, FieldValue>, frame: DataFrame): void {
    const anchorFv = fields.get("event_timestamp");
    if (anchorFv !== undefined) {
      const raws = Array.isArray(anchorFv.raw) ? anchorFv.raw : [anchorFv.raw];
      for (let i = raws.length - 1; i >= 0; i--) {
        const r = raws[i];
        if (typeof r === "number" && r !== 0xffffffff) {
          this.hrTs1024 = r;
          break;
        }
      }
    }
    const packed = fields.get("event_timestamp_12");
    if (packed === undefined || !(packed.raw instanceof Uint8Array)) return;
    if (this.hrTs1024 === null) {
      this.diag(
        "HR_EXPANSION_NO_ANCHOR",
        "hr.event_timestamp_12 present before any full event_timestamp; samples not expandable",
        "hr",
      );
      return;
    }
    // Python builds an arbitrary-precision int from the whole buffer; bigint here,
    // because the packed field routinely exceeds 6 bytes.
    let total = 0n;
    for (let i = packed.raw.length - 1; i >= 0; i--) {
      total = (total << 8n) | BigInt(packed.raw[i] as number);
    }
    const n = Math.floor((packed.raw.length * 8) / 12);
    let anchor = this.hrTs1024;
    const outRaw: number[] = [];
    for (let i = 0; i < n; i++) {
      const v = Number((total >> BigInt(12 * i)) & 0xfffn);
      if (v === 0xfff) continue;
      const low12 = anchor % 4096;
      anchor = anchor - low12 + v + (v < low12 ? 0x1000 : 0);
      outRaw.push(anchor);
    }
    this.hrTs1024 = anchor;
    if (outRaw.length > 0) {
      fields.set(
        "event_timestamp_expanded",
        fv(
          outRaw.map((r) => r / 1024.0),
          outRaw,
          "s",
        ),
      );
      this.salvage(
        frame.definition.offset,
        10,
        `event_timestamp_12 expanded into ${outRaw.length} sample timestamp(s)`,
        frame.offset,
      );
    }
  }

  private decodeBalance(fields: Map<string, FieldValue>): void {
    const specs: [string, number, number, number][] = [
      ["left_right_balance", 0x80, 0x7f, 1.0],
      ["left_right_balance_100", 0x8000, 0x3fff, 100.0],
    ];
    for (const [fname, flagBit, mask, scale] of specs) {
      const field = fields.get(fname);
      if (field === undefined || typeof field.raw !== "number") continue;
      const val = field.raw & mask;
      const pct = val / scale;
      if (pct > 100.0) continue; // not plausibly a percentage
      const right = Boolean(field.raw & flagBit);
      fields.set("right_balance_pct", fv(right ? pct : 100.0 - pct, field.raw, "percent"));
    }
  }

  private resolveProduct(fields: Map<string, FieldValue>): void {
    const manu = fields.get("manufacturer");
    const prod = fields.get("product");
    if (manu === undefined || prod === undefined || typeof prod.value !== "number") return;
    let enumName: string | null = null;
    if (
      manu.value === "garmin" ||
      manu.value === "dynastream" ||
      manu.value === "dynastream_oem" ||
      manu.value === "tacx"
    ) {
      enumName = "garmin_product";
    } else if (manu.value === "favero_electronics") {
      enumName = "favero_product";
    }
    if (enumName === null) return;
    const mapped = ENUMS[enumName]?.[prod.value];
    if (mapped !== undefined) {
      fields.set("product", fv(mapped, prod.raw, prod.units, prod.developer));
    }
  }

  private static readonly TIMER_TRIGGER: Readonly<Record<number, string>> = {
    0: "manual",
    1: "auto",
    2: "fitness_equipment",
  };

  private resolveEventSubfield(fields: Map<string, FieldValue>): void {
    const ev = fields.get("event");
    const data = fields.get("data");
    if (ev === undefined || data === undefined || typeof data.raw !== "number") return;
    if (ev.value === "timer" && !fields.has("timer_trigger")) {
      const mapped = Decoder.TIMER_TRIGGER[data.raw];
      fields.set("timer_trigger", fv(mapped !== undefined ? mapped : data.raw, data.raw));
    }
  }

  private salvage(
    defOffset: number,
    fieldNum: number,
    why: string,
    firstOffset: number,
    defectCode: string | null = null,
    defectDetail: string | null = null,
  ): void {
    const key = `${defOffset} ${fieldNum} ${why}`;
    const entry = this.salvageAgg.get(key);
    if (entry === undefined) {
      this.salvageAgg.set(key, [1, firstOffset, defOffset, fieldNum, why]);
      if (defectCode !== null) {
        // Surfaced once; strict mode raises on it.
        this.out.defects.push(defect(defectCode, defectDetail ?? why, firstOffset, "data"));
      }
    } else {
      entry[0] += 1;
    }
  }

  private diag(code: string, detail: string, scope: string): void {
    const key = `${code} ${scope}`;
    if (this.diagSeen.has(key)) return;
    this.diagSeen.add(key);
    this.out.diagnostics.push({ code, detail, scope });
  }
}
