/**
 * FIT encoder — canonical wire form (ADR-0006).
 *
 * Twin of `python/src/chiptime/encode.py`. Two producers feed `encodeMessages`:
 * - `encodableFromMessage`: lossless re-emit of a decoded Message (unknown content
 *   included; compressed-header timestamps materialized as field 253).
 * - `encodableFromProfile`: synthesize a message from profile names/values
 *   (repair's session/activity/events).
 *
 * This is a programming surface, not a hostile-input surface: bad inputs throw
 * `EncodeError` instead of becoming defects.
 */

import { crc16 } from "./frames.js";
import type { Message } from "./message.js";
import { pyRound } from "./numeric.js";
import { BASE_TYPES, BASE_TYPES_BY_NAME, ENUMS, MESSAGES } from "./profile/index.js";
import type { BaseType } from "./profile/index.js";

export const HEADER_SIZE = 14;
export const PROTOCOL_VERSION = 0x20;
export const PROFILE_VERSION = 21141;

export class EncodeError extends Error {
  override readonly name = "EncodeError";
}

/** Wire-ready field value (sentinel substitution done by the encoder). */
export interface FieldSpecValue {
  readonly num: number;
  readonly baseType: number;
  readonly raw: unknown; // number | bigint | Uint8Array | array | null
  readonly size: number;
}

export interface DevSpecValue {
  readonly num: number;
  readonly size: number;
  readonly devIndex: number;
  readonly raw: Uint8Array;
}

export interface EncodableMessage {
  readonly globalNum: number;
  readonly specs: readonly FieldSpecValue[];
  readonly devSpecs: readonly DevSpecValue[];
}

/** Python compares shape tuples; a string key is the JS equivalent. */
function shapeKey(em: EncodableMessage): string {
  const f = em.specs.map((s) => `${s.num},${s.baseType},${s.size}`).join(";");
  const d = em.devSpecs.map((s) => `${s.num},${s.size},${s.devIndex}`).join(";");
  return `${em.globalNum}|${f}|${d}`;
}

class Slots {
  private byShape = new Map<string, number>();
  private shapes = new Map<number, string>();
  private nextSlot = 0;

  /** Returns [localId, needsDefinition]. */
  get(shape: string): [number, boolean] {
    const existing = this.byShape.get(shape);
    if (existing !== undefined) return [existing, false];
    const local = this.nextSlot;
    this.nextSlot = (this.nextSlot + 1) % 16;
    const old = this.shapes.get(local);
    if (old !== undefined) this.byShape.delete(old);
    this.byShape.set(shape, local);
    this.shapes.set(local, shape);
    return [local, true];
  }
}

class ByteSink {
  private buf = new Uint8Array(1 << 12);
  len = 0;

  private ensure(extra: number): void {
    if (this.len + extra <= this.buf.length) return;
    let size = this.buf.length * 2;
    while (size < this.len + extra) size *= 2;
    const next = new Uint8Array(size);
    next.set(this.buf.subarray(0, this.len));
    this.buf = next;
  }

  byte(b: number): void {
    this.ensure(1);
    this.buf[this.len++] = b;
  }

  bytes(bs: Uint8Array | number[]): void {
    this.ensure(bs.length);
    for (const b of bs) this.buf[this.len++] = b as number;
  }

  u16le(v: number): void {
    this.ensure(2);
    this.buf[this.len++] = v & 0xff;
    this.buf[this.len++] = (v >> 8) & 0xff;
  }

  u32le(v: number): void {
    this.ensure(4);
    this.buf[this.len++] = v & 0xff;
    this.buf[this.len++] = (v >>> 8) & 0xff;
    this.buf[this.len++] = (v >>> 16) & 0xff;
    this.buf[this.len++] = (v >>> 24) & 0xff;
  }

  result(): Uint8Array {
    return this.buf.slice(0, this.len);
  }
}

/** Pack one numeric element of `bt` at little endian, Python `struct.pack` style. */
function packElement(out: ByteSink, bt: BaseType, v: number | bigint, fieldNum: number): void {
  const dv = new DataView(new ArrayBuffer(8));
  try {
    switch (bt.accessor) {
      case "getInt8":
        checkRange(v, -0x80, 0x7f, bt.name, fieldNum);
        dv.setInt8(0, Number(v));
        break;
      case "getUint8":
        checkRange(v, 0, 0xff, bt.name, fieldNum);
        dv.setUint8(0, Number(v));
        break;
      case "getInt16":
        checkRange(v, -0x8000, 0x7fff, bt.name, fieldNum);
        dv.setInt16(0, Number(v), true);
        break;
      case "getUint16":
        checkRange(v, 0, 0xffff, bt.name, fieldNum);
        dv.setUint16(0, Number(v), true);
        break;
      case "getInt32":
        checkRange(v, -0x80000000, 0x7fffffff, bt.name, fieldNum);
        dv.setInt32(0, Number(v), true);
        break;
      case "getUint32":
        checkRange(v, 0, 0xffffffff, bt.name, fieldNum);
        dv.setUint32(0, Number(v), true);
        break;
      case "getFloat32":
        dv.setFloat32(0, Number(v), true);
        break;
      case "getFloat64":
        dv.setFloat64(0, Number(v), true);
        break;
      case "getBigInt64":
        dv.setBigInt64(0, BigInt(v as number | bigint), true);
        break;
      case "getBigUint64":
        dv.setBigUint64(0, BigInt(v as number | bigint), true);
        break;
      default:
        throw new EncodeError(`field ${fieldNum}: cannot pack ${bt.name}`);
    }
  } catch (e) {
    if (e instanceof EncodeError) throw e;
    throw new EncodeError(`field ${fieldNum}: ${String(v)} does not fit ${bt.name}`);
  }
  for (let i = 0; i < bt.size; i++) out.byte(dv.getUint8(i));
}

function checkRange(v: number | bigint, lo: number, hi: number, name: string, num: number): void {
  // Python's struct raises on out-of-range and on non-integral ints alike.
  const n = typeof v === "bigint" ? v : v;
  if (typeof n === "number" && !Number.isInteger(n)) {
    throw new EncodeError(`field ${num}: ${n} does not fit ${name}`);
  }
  const bn = typeof n === "bigint" ? n : BigInt(Math.trunc(n as number));
  if (bn < BigInt(lo) || bn > BigInt(hi)) {
    throw new EncodeError(`field ${num}: ${n} does not fit ${name}`);
  }
}

const SIGNED_INVALID: Readonly<Record<string, number | bigint>> = {
  sint8: 0x7f,
  sint16: 0x7fff,
  sint32: 0x7fffffff,
  sint64: 0x7fffffffffffffffn,
};

function invalidRaw(btName: string): number | bigint {
  const signed = SIGNED_INVALID[btName];
  if (signed !== undefined) return signed;
  const inv = BASE_TYPES_BY_NAME[btName]?.invalid;
  if (inv === null || inv === undefined) {
    throw new EncodeError(`no invalid sentinel for ${btName}`);
  }
  return inv;
}

export function encodeMessages(messages: readonly EncodableMessage[]): Uint8Array {
  const body = new ByteSink();
  const slots = new Slots();
  for (const em of messages) {
    const [local, needsDef] = slots.get(shapeKey(em));
    if (needsDef) writeDefinition(body, local, em);
    writeData(body, local, em);
  }
  const bodyBytes = body.result();

  const head = new ByteSink();
  head.byte(HEADER_SIZE);
  head.byte(PROTOCOL_VERSION);
  head.u16le(PROFILE_VERSION);
  head.u32le(bodyBytes.length);
  head.bytes([0x2e, 0x46, 0x49, 0x54]); // ".FIT"
  const head12 = head.result();
  head.u16le(crc16(head12));

  const out = new ByteSink();
  out.bytes(head.result());
  out.bytes(bodyBytes);
  const whole = out.result();
  out.u16le(crc16(whole));
  return out.result();
}

function writeDefinition(out: ByteSink, local: number, em: EncodableMessage): void {
  if (em.specs.length > 255) {
    throw new EncodeError(`message ${em.globalNum}: too many fields`);
  }
  const hdr = 0x40 | (em.devSpecs.length > 0 ? 0x20 : 0x00) | local;
  out.bytes([hdr, 0, 0]); // little-endian always (ADR-0006)
  out.u16le(em.globalNum);
  out.byte(em.specs.length);
  for (const s of em.specs) {
    if (!(s.size > 0 && s.size < 256)) {
      throw new EncodeError(`field ${s.num}: size ${s.size} out of range`);
    }
    out.bytes([s.num, s.size, s.baseType]);
  }
  if (em.devSpecs.length > 0) {
    out.byte(em.devSpecs.length);
    for (const d of em.devSpecs) out.bytes([d.num, d.size, d.devIndex]);
  }
}

function writeData(out: ByteSink, local: number, em: EncodableMessage): void {
  out.byte(local);
  for (const s of em.specs) {
    const bt = BASE_TYPES[s.baseType];
    if (bt === undefined || bt.accessor === null) {
      // string/byte/unknown -> raw bytes
      const raw =
        s.raw instanceof Uint8Array
          ? s.raw
          : s.raw === null || s.raw === undefined
            ? new Uint8Array(0)
            : Uint8Array.from(s.raw as ArrayLike<number>);
      if (raw.length > s.size) {
        throw new EncodeError(`field ${s.num}: ${raw.length} bytes exceeds size ${s.size}`);
      }
      out.bytes(raw);
      const pad = bt === undefined ? 0xff : 0x00;
      for (let i = raw.length; i < s.size; i++) out.byte(pad);
      continue;
    }
    const count = Math.floor(s.size / bt.size);
    const vals: unknown[] = Array.isArray(s.raw) ? [...s.raw] : [s.raw];
    if (vals.length > count) {
      throw new EncodeError(`field ${s.num}: ${vals.length} values exceed count ${count}`);
    }
    while (vals.length < count) vals.push(null);
    for (const v of vals) {
      if (v === null || v === undefined) {
        if (bt.name === "float32" || bt.name === "float64") {
          // the exact invalid pattern, not an arbitrary NaN (muktihari#39)
          for (let i = 0; i < bt.size; i++) out.byte(0xff);
          continue;
        }
        packElement(out, bt, invalidRaw(bt.name), s.num);
        continue;
      }
      if (typeof v !== "number" && typeof v !== "bigint") {
        throw new EncodeError(`field ${s.num}: ${String(v)} does not fit ${bt.name}`);
      }
      packElement(out, bt, v, s.num);
    }
  }
  for (const d of em.devSpecs) {
    if (d.raw.length !== d.size) {
      throw new EncodeError(`dev field ${d.num}: ${d.raw.length} bytes != size ${d.size}`);
    }
    out.bytes(d.raw);
  }
}

// ── producers ───────────────────────────────────────────────────────────────

/** uint type code by width — the canonical numeric form for a reassembled field. */
const UINT_BY_SIZE: Readonly<Record<number, number>> = { 1: 0x02, 2: 0x84, 4: 0x86, 8: 0x8f };

/**
 * Base type to re-emit a field in.
 *
 * Normally the wire type, but decode sometimes *reassembles* a field a broken
 * encoder mis-declared — field 253 written as `byte[4]` when it is a timestamp
 * (taxonomy #17/#88, the Xiaomi-pipeline class). Emitting the numeric type the
 * value actually is produces the canonical wire form (ADR-0006); the
 * reinterpretation was already announced at parse time.
 */
function canonicalBaseType(baseType: number, raw: unknown, size: number): number {
  const bt = BASE_TYPES[baseType];
  if (bt !== undefined && bt.accessor !== null) return baseType; // already numeric
  const isInt = (typeof raw === "number" && Number.isInteger(raw)) || typeof raw === "bigint";
  if (!isInt) return baseType; // genuine strings/bytes are untouched
  return UINT_BY_SIZE[size] ?? baseType;
}

const FIELD_NUM_RE = /^field_(\d+)$/;

/** Lossless re-emit from a decoded message's wire definition + raw values. */
export function encodableFromMessage(msg: Message): EncodableMessage {
  if (msg.wire === null) {
    throw new EncodeError(`message ${msg.name} has no wire definition; use encodableFromProfile`);
  }
  const byNum = new Map<number, unknown>();
  const devByKey = new Map<string, unknown>();
  const mdef = MESSAGES[msg.globalNum];
  const nameToNum = new Map<string, number>();
  if (mdef) {
    for (const [n, f] of Object.entries(mdef.fields)) nameToNum.set(f.name, Number(n));
  }
  for (const [fname, fv] of msg.fields) {
    if (fv.developer !== null) {
      devByKey.set(
        `${fv.developer.developerDataIndex}:${fv.developer.fieldDefinitionNumber}`,
        fv.raw,
      );
      continue;
    }
    if (fname === "timestamp") {
      byNum.set(253, fv.raw);
    } else if (nameToNum.has(fname)) {
      // profile name wins (field_description has a real field NAMED field_definition_number)
      byNum.set(nameToNum.get(fname) as number, fv.raw);
    } else {
      const m = FIELD_NUM_RE.exec(fname);
      if (m !== null) byNum.set(Number(m[1]), fv.raw);
    }
  }
  const specs: FieldSpecValue[] = [];
  let seen253 = false;
  for (const ws of msg.wire.fields) {
    seen253 = seen253 || ws.num === 253;
    const raw = byNum.get(ws.num) ?? null;
    specs.push({
      num: ws.num,
      baseType: canonicalBaseType(ws.baseType, raw, ws.size),
      raw,
      size: ws.size,
    });
  }
  if (!seen253 && msg.fields.has("timestamp")) {
    // compressed-header timestamp materialized (ADR-0006 §2)
    const tsRaw = msg.fields.get("timestamp")?.raw ?? null;
    specs.push({ num: 253, baseType: 0x86, raw: tsRaw, size: 4 });
  }
  const devSpecs = msg.wire.devFields.map((ds) => ({
    num: ds.num,
    size: ds.size,
    devIndex: ds.devDataIndex,
    raw: devBytes(devByKey.get(`${ds.devDataIndex}:${ds.num}`) ?? null, ds.size),
  }));
  return { globalNum: msg.globalNum, specs, devSpecs };
}

/** Re-pack a decoded dev-field raw value into its wire bytes. */
function devBytes(raw: unknown, size: number): Uint8Array {
  if (raw === null || raw === undefined) return new Uint8Array(size).fill(0xff);
  if (raw instanceof Uint8Array) {
    if (raw.length !== size) {
      throw new EncodeError(`dev field bytes ${raw.length} != size ${size}`);
    }
    return raw;
  }
  if (typeof raw === "bigint" || (typeof raw === "number" && Number.isInteger(raw))) {
    // Python: raw.to_bytes(size, "little", signed=raw < 0)
    let v = typeof raw === "bigint" ? raw : BigInt(raw);
    const negative = v < 0n;
    if (negative) v += 1n << BigInt(size * 8); // two's complement
    const out = new Uint8Array(size);
    for (let i = 0; i < size; i++) {
      out[i] = Number(v & 0xffn);
      v >>= 8n;
    }
    if (v !== 0n) throw new EncodeError(`dev field value does not fit ${size} byte(s)`);
    return out;
  }
  if (typeof raw === "number") {
    const dv = new DataView(new ArrayBuffer(size));
    if (size === 4) dv.setFloat32(0, raw, true);
    else if (size === 8) dv.setFloat64(0, raw, true);
    else throw new EncodeError(`float dev field with size ${size}`);
    return new Uint8Array(dv.buffer);
  }
  if (Array.isArray(raw)) {
    if (raw.length === 0) return new Uint8Array(size).fill(0xff);
    const per = Math.floor(size / raw.length);
    const parts = raw.map((v) => devBytes(v, per));
    const out = new Uint8Array(size);
    let at = 0;
    for (const p of parts) {
      out.set(p, at);
      at += p.length;
    }
    return out;
  }
  throw new EncodeError(`cannot re-pack dev value ${String(raw)}`);
}

/** Wire types for profile-synthesized fields (canonical choices). */
const SYNTH_TYPES: Readonly<Record<string, string>> = {
  timestamp: "uint32",
  start_time: "uint32",
  local_timestamp: "uint32",
  time_created: "uint32",
};

/** Synthesize a message from profile field names + semantic values. */
export function encodableFromProfile(
  globalNum: number,
  values: Readonly<Record<string, unknown>>,
): EncodableMessage {
  const mdef = MESSAGES[globalNum];
  if (mdef === undefined) {
    throw new EncodeError(
      `unknown global message ${globalNum}; profile synthesis needs a known message`,
    );
  }
  const byName = new Map<
    string,
    { num: number; name: string; kind: string; scale: number; offset: number }
  >();
  for (const f of Object.values(mdef.fields)) byName.set(f.name, f);
  const specs: FieldSpecValue[] = [];
  for (const [fname, value] of Object.entries(values)) {
    const fdef = byName.get(fname);
    if (fdef === undefined) {
      throw new EncodeError(`${mdef.name} has no field '${fname}'`);
    }
    const [btName, raw, size] = reverse(fdef, value);
    const bt = BASE_TYPES_BY_NAME[btName] as BaseType;
    specs.push({ num: fdef.num, baseType: bt.byte, raw, size });
  }
  return { globalNum, specs, devSpecs: [] };
}

const UTF8_ENCODER = new TextEncoder();

function reverse(
  fdef: { name: string; kind: string; scale: number; offset: number },
  value: unknown,
): [string, unknown, number] {
  const kind = fdef.kind;
  if (kind === "date_time" || kind === "local_date_time") {
    if (typeof value !== "number" || !Number.isInteger(value)) {
      throw new EncodeError(`${fdef.name}: expected FIT seconds`);
    }
    return ["uint32", value, 4];
  }
  if (kind.startsWith("enum:")) {
    const mapping = ENUMS[kind.slice(5)] ?? {};
    let raw: number;
    if (typeof value === "string") {
      let found: number | null = null;
      for (const [k, v] of Object.entries(mapping)) {
        if (v === value) found = Number(k); // last match wins, as Python's dict-reverse does
      }
      if (found === null) {
        throw new EncodeError(`${fdef.name}: unknown enum name '${value}'`);
      }
      raw = found;
    } else {
      raw = Math.trunc(Number(value));
    }
    const ebt = fdef.name === "manufacturer" || fdef.name === "manufacturer_id" ? "uint16" : "enum";
    return [ebt, raw, (BASE_TYPES_BY_NAME[ebt] as BaseType).size];
  }
  if (kind === "string") {
    const bytes = UTF8_ENCODER.encode(String(value));
    const withNul = new Uint8Array(bytes.length + 1);
    withNul.set(bytes);
    return ["string", withNul, withNul.length];
  }
  if (kind === "bytes") {
    const braw = value instanceof Uint8Array ? value : Uint8Array.from(value as ArrayLike<number>);
    return ["byte", braw, braw.length];
  }
  // numbers: reverse scale/offset; choose a wide-enough canonical type.
  // pyRound: Python's round() is half-to-even and this reaches the wire.
  const rawNum = pyRound((Number(value) + fdef.offset) * fdef.scale);
  let bt = SYNTH_TYPES[fdef.name];
  if (bt === undefined) {
    if (
      fdef.name === "message_index" ||
      fdef.name === "num_laps" ||
      fdef.name === "first_lap_index"
    ) {
      bt = "uint16";
    } else if (rawNum < 0) {
      bt = "sint32";
    } else if (rawNum <= 0xfe) {
      bt = "uint8";
    } else if (rawNum <= 0xfffe) {
      bt = "uint16";
    } else {
      bt = "uint32";
    }
  }
  return [bt, rawNum, (BASE_TYPES_BY_NAME[bt] as BaseType).size];
}
