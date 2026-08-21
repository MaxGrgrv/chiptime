/**
 * Wire-level frame reader. Never raises on content (ADR-0003).
 *
 * Twin of `python/src/chiptime/frames.py`. Reads ONE FIT stream (header + body +
 * CRC trailer) from `data` starting at `offset`; chained files are handled by the
 * caller reading again from `EndOfStream.consumed`.
 *
 * The design promise is that this module is *incapable* of crashing on hostile
 * input (PRD section 6.1). Two consequences shape the code:
 *
 *   - Every read is bounds-checked before it happens. `DataView` throws `RangeError`
 *     past the end, and a `try`/`catch` around the loop would convert a bounds bug
 *     into silent truncation -- which is the failure mode contract #1 forbids.
 *   - `MAX_RESYNCS` and `PREAMBLE_SCAN_LIMIT` are anti-hang bounds, not tuning. A
 *     resync loop without them turns a corrupt file into a frozen browser tab.
 */

import type { Defect, Severity } from "./errors.js";
import { defect } from "./errors.js";
import { BASE_TYPES } from "./profile/base-types.js";

const MAGIC = [0x2e, 0x46, 0x49, 0x54]; // ".FIT"

const CRC_TABLE = [
  0x0000, 0xcc01, 0xd801, 0x1400, 0xf001, 0x3c00, 0x2800, 0xe401, 0xa001, 0x6c00, 0x7800, 0xb401,
  0x5000, 0x9c01, 0x8801, 0x4400,
];

function nibbleStep(seed: number, byte: number): number {
  let crc = seed;
  let tmp = CRC_TABLE[crc & 0xf] as number;
  crc = (crc >> 4) & 0x0fff;
  crc = crc ^ tmp ^ (CRC_TABLE[byte & 0xf] as number);
  tmp = CRC_TABLE[crc & 0xf] as number;
  crc = (crc >> 4) & 0x0fff;
  return crc ^ tmp ^ (CRC_TABLE[(byte >> 4) & 0xf] as number);
}

// Byte-wise table composed from the FIT nibble algorithm (Python's F20 perf pass).
// The identity step(crc, b) === (crc >> 8) ^ T[(crc ^ b) & 0xFF] is property-tested.
const CRC256 = Array.from({ length: 256 }, (_, b) => nibbleStep(0, b));

export function crc16(data: Uint8Array, seed = 0): number {
  let crc = seed;
  for (const byte of data) {
    crc = (crc >> 8) ^ (CRC256[(crc ^ byte) & 0xff] as number);
  }
  return crc;
}

// ── frame events ────────────────────────────────────────────────────────────
// Python discriminates by class; TypeScript needs a tag it can narrow on. The
// `kind` field is the one structural difference from the Python types, and the
// parity dump maps it back to the class names.

export interface FileHeader {
  readonly kind: "header";
  readonly offset: number;
  readonly size: number;
  readonly protocolVersion: number;
  readonly profileVersion: number;
  readonly dataSize: number;
  readonly magicOk: boolean;
  /** `null`: a 12-byte header has no CRC. */
  readonly crcDeclared: number | null;
  /** `null`: absent or zero -- a legal skip (taxonomy #5). */
  readonly crcOk: boolean | null;
}

export interface FieldSpec {
  readonly num: number;
  readonly size: number;
  readonly baseType: number;
}

export interface DevFieldSpec {
  readonly num: number;
  readonly size: number;
  readonly devDataIndex: number;
}

export interface DefinitionFrame {
  readonly kind: "definition";
  readonly offset: number;
  readonly localId: number;
  readonly globalNum: number;
  readonly bigEndian: boolean;
  readonly fields: readonly FieldSpec[];
  readonly devFields: readonly DevFieldSpec[];
}

export function payloadSize(frame: DefinitionFrame): number {
  let total = 0;
  for (const f of frame.fields) total += f.size;
  for (const f of frame.devFields) total += f.size;
  return total;
}

export interface DataFrame {
  readonly kind: "data";
  readonly offset: number;
  readonly localId: number;
  readonly definition: DefinitionFrame;
  readonly payload: Uint8Array;
  /** Set for compressed-timestamp headers (taxonomy #21). */
  readonly timeOffset: number | null;
}

export interface CrcFrame {
  readonly kind: "crc";
  readonly offset: number;
  readonly declared: number;
  readonly computed: number;
  readonly ok: boolean;
}

export interface SkippedBytes {
  readonly kind: "skipped";
  readonly offset: number;
  readonly length: number;
  readonly reason: string;
}

export interface EndOfStream {
  readonly kind: "eos";
  /** Absolute offset just past this FIT stream. */
  readonly consumed: number;
}

/** A `Defect` carried as a frame event; tagged so it narrows alongside the rest. */
export interface DefectEvent extends Defect {
  readonly kind: "defect";
}

export type FrameEvent =
  | FileHeader
  | DefinitionFrame
  | DataFrame
  | CrcFrame
  | SkippedBytes
  | DefectEvent
  | EndOfStream;

function defectEvent(code: string, detail: string, offset: number, sev: Severity): DefectEvent {
  return { kind: "defect", ...defect(code, detail, offset, sev) };
}

export const MAX_RESYNCS = 64; // pathological files degrade to prefix salvage, never hang
export const PREAMBLE_SCAN_LIMIT = 4096;
const MAX_DEF_PAYLOAD = 2048; // implausibly large payloads reject a resync candidate

/**
 * Read one byte.
 *
 * Every call site bounds-checks first, exactly as the Python does (where an
 * unchecked read would raise `IndexError`). The `?? 0` is unreachable, and it is a
 * deliberate choice over a non-null assertion: if a bounds check were ever wrong,
 * this module must still not throw. Position always advances or the loop breaks, so
 * a spurious 0 cannot spin.
 */
function u8(data: Uint8Array, i: number): number {
  return data[i] ?? 0;
}

function hasMagicAt(data: Uint8Array, at: number): boolean {
  for (let i = 0; i < 4; i++) {
    if (data[at + i] !== MAGIC[i]) return false;
  }
  return true;
}

function findMagic(data: Uint8Array, from: number, limit: number): number {
  const stop = Math.min(limit, data.length) - 3;
  for (let p = from; p < stop; p++) {
    if (hasMagicAt(data, p)) return p;
  }
  return -1;
}

/**
 * If a plausible definition frame starts at `p`, return its end offset, local id and
 * payload size; otherwise `null`. Stricter than the main reader: reserved bit 4 must
 * be clear, every base type known, sizes positive multiples.
 */
function plausibleDefinition(
  data: Uint8Array,
  p: number,
  end: number,
): { q: number; local: number; size: number } | null {
  const hdr = u8(data, p);
  if (hdr & 0x80 || !(hdr & 0x40) || hdr & 0x10) return null;
  const hasDev = Boolean(hdr & 0x20);
  let q = p + 1;
  if (q + 5 > end) return null;
  const arch = u8(data, q + 1);
  if (arch !== 0 && arch !== 1) return null;
  const nf = u8(data, q + 4);
  if (nf < 1) return null; // modern Garmin definitions exceed 100 fields
  q += 5;
  if (q + nf * 3 > end) return null;
  let total = 0;
  for (let i = 0; i < nf; i++) {
    const size = u8(data, q + 1);
    const btb = u8(data, q + 2);
    const bt = BASE_TYPES[btb];
    if (bt === undefined || size === 0 || (bt.accessor !== null && size % bt.size !== 0)) {
      return null;
    }
    total += size;
    q += 3;
  }
  if (hasDev) {
    if (q + 1 > end) return null;
    const nd = u8(data, q);
    if (nd > 32) return null;
    q += 1;
    if (q + nd * 3 > end) return null;
    for (let i = 0; i < nd; i++) {
      total += u8(data, q + 1);
      q += 3;
    }
  }
  if (total > MAX_DEF_PAYLOAD) return null;
  return { q, local: hdr & 0x0f, size: total };
}

/**
 * One-frame lookahead: the bytes after a candidate definition must themselves start
 * a plausible frame.
 */
function lookaheadOk(
  data: Uint8Array,
  q: number,
  end: number,
  localDefs: Map<number, DefinitionFrame>,
  localSizes: Map<number, number>,
  candLocal: number,
  candSize: number,
): boolean {
  if (q >= end) return true;
  const b = u8(data, q);
  let local: number;
  if (b & 0x80) {
    local = (b >> 5) & 0x03;
  } else if (b & 0x40) {
    return !(b & 0x10); // another definition header (shallow check)
  } else {
    local = b & 0x0f;
  }
  let size: number;
  if (local === candLocal) {
    size = candSize;
  } else if (localDefs.has(local)) {
    size = localSizes.get(local) as number;
  } else {
    return false;
  }
  return q + 1 + size <= end;
}

function findNextDefinition(
  data: Uint8Array,
  fromPos: number,
  end: number,
  localDefs: Map<number, DefinitionFrame>,
  localSizes: Map<number, number>,
): number | null {
  for (let p = fromPos; p < end; p++) {
    const cand = plausibleDefinition(data, p, end);
    if (cand === null) continue;
    if (lookaheadOk(data, cand.q, end, localDefs, localSizes, cand.local, cand.size)) return p;
  }
  return null;
}

export function* readStream(
  data: Uint8Array,
  options: { offset?: number } = {},
): Generator<FrameEvent> {
  const n = data.length;
  let start = options.offset ?? 0;
  let avail = n - start;
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);

  if (avail === 0) {
    yield defectEvent("FIT_EMPTY", "file contains no bytes", start, "fatal");
    yield { kind: "eos", consumed: n };
    return;
  }
  if (avail < 12) {
    yield defectEvent(
      "FIT_TOO_SMALL",
      `only ${avail} bytes; smallest valid FIT header is 12`,
      start,
      "fatal",
    );
    yield { kind: "eos", consumed: n };
    return;
  }

  let hsize = u8(data, start);
  let magicOk = hasMagicAt(data, start + 8);
  if (hsize !== 12 && hsize !== 14 && !magicOk) {
    // Preamble garbage before the real header (taxonomy #9, Edge 1050 class):
    // scan ahead for the magic and re-anchor.
    const m = findMagic(data, start, start + PREAMBLE_SCAN_LIMIT);
    if (m >= 0 && m - 8 > start && u8(data, m - 8) >= 12 && u8(data, m - 8) <= 64) {
      const skipped = m - 8 - start;
      yield defectEvent(
        "FIT_HEADER_INVALID",
        `${skipped} garbage byte(s) before the FIT header`,
        start,
        "structural",
      );
      yield { kind: "skipped", offset: start, length: skipped, reason: "preamble-garbage" };
      start = m - 8;
      avail = n - start;
      hsize = u8(data, start);
      magicOk = true;
    }
  }
  if (hsize !== 12 && hsize !== 14) {
    if (magicOk && hsize >= 12 && hsize <= 64 && start + hsize <= n) {
      yield defectEvent(
        "FIT_HEADER_INVALID",
        `nonstandard header size ${hsize}; '.FIT' magic present, proceeding`,
        start,
        "structural",
      );
    } else if (magicOk) {
      yield defectEvent(
        "FIT_HEADER_INVALID",
        `invalid header size ${hsize}; '.FIT' magic present, assuming 14`,
        start,
        "structural",
      );
      hsize = avail >= 14 ? 14 : 12;
    } else {
      yield defectEvent(
        "NOT_FIT_FORMAT",
        `no '.FIT' magic and invalid header size ${hsize}`,
        start,
        "fatal",
      );
      yield { kind: "eos", consumed: n };
      return;
    }
  } else if (!magicOk) {
    yield defectEvent(
      "FIT_HEADER_INVALID",
      "'.FIT' magic missing from header; proceeding",
      start,
      "structural",
    );
  }

  const protocol = u8(data, start + 1);
  const profileVer = view.getUint16(start + 2, true);
  const dataSize = view.getUint32(start + 4, true);

  let crcDeclared: number | null = null;
  let crcOk: boolean | null = null;
  if (hsize >= 14 && start + 14 <= n) {
    crcDeclared = view.getUint16(start + 12, true);
    if (crcDeclared !== 0) {
      // 0x0000 = legal "no check" (taxonomy #5)
      const computedHdr = crc16(data.subarray(start, start + 12));
      crcOk = computedHdr === crcDeclared;
      if (!crcOk) {
        yield defectEvent(
          "FIT_HEADER_CRC_MISMATCH",
          `header CRC 0x${hex4(crcDeclared)} != computed 0x${hex4(computedHdr)}`,
          start + 12,
          "structural",
        );
      }
    }
  }

  yield {
    kind: "header",
    offset: start,
    size: hsize,
    protocolVersion: protocol,
    profileVersion: profileVer,
    dataSize,
    magicOk,
    crcDeclared,
    crcOk,
  };

  const bodyStart = start + hsize;
  const declaredEnd = bodyStart + dataSize;
  const truncatedDeclared = declaredEnd > n;
  let end = truncatedDeclared ? n : declaredEnd;
  if (!truncatedDeclared && dataSize === 0 && n - bodyStart > 2) {
    yield defectEvent(
      "FIT_DATA_SIZE_MISMATCH",
      `header declares 0 data bytes but ${n - bodyStart} are present; trusting content`,
      start + 4,
      "structural",
    );
    end = n - 2;
  }

  const localDefs = new Map<number, DefinitionFrame>();
  const localSizes = new Map<number, number>();
  let pos = bodyStart;
  let stopped = false;
  let resyncs = 0;

  const resync = (badPos: number, code: string): { skip: SkippedBytes; next: number } => {
    let nxt: number | null = null;
    if (resyncs < MAX_RESYNCS) {
      nxt = findNextDefinition(data, badPos + 1, end, localDefs, localSizes);
    }
    if (nxt === null) {
      return {
        skip: { kind: "skipped", offset: badPos, length: end - badPos, reason: code },
        next: end,
      };
    }
    return {
      skip: { kind: "skipped", offset: badPos, length: nxt - badPos, reason: code },
      next: nxt,
    };
  };

  while (pos < end) {
    const hdr = u8(data, pos);
    if (hdr & 0x80) {
      // compressed-timestamp data message
      const local = (hdr >> 5) & 0x03;
      const toff = hdr & 0x1f;
      const df = localDefs.get(local);
      if (df === undefined) {
        yield defectEvent(
          "FIT_UNDEFINED_LOCAL_TYPE",
          `compressed data message references undefined local type ${local}`,
          pos,
          "structural",
        );
        const r = resync(pos, "FIT_UNDEFINED_LOCAL_TYPE");
        pos = r.next;
        resyncs += 1;
        yield r.skip;
        continue;
      }
      const size = localSizes.get(local) as number;
      if (pos + 1 + size > end) {
        yield defectEvent(
          "FIT_TRUNCATED",
          `record at byte ${pos} needs ${size} payload bytes; only ${end - pos - 1} remain`,
          pos,
          "structural",
        );
        stopped = true;
        break;
      }
      yield {
        kind: "data",
        offset: pos,
        localId: local,
        definition: df,
        payload: data.subarray(pos + 1, pos + 1 + size),
        timeOffset: toff,
      };
      pos += 1 + size;
    } else if (hdr & 0x40) {
      // definition message
      const local = hdr & 0x0f;
      const hasDev = Boolean(hdr & 0x20);
      let p = pos + 1;
      if (p + 5 > end) {
        yield defectEvent(
          "FIT_TRUNCATED",
          "file ends inside a definition message",
          pos,
          "structural",
        );
        stopped = true;
        break;
      }
      const arch = u8(data, p + 1);
      if (arch !== 0 && arch !== 1) {
        yield defectEvent(
          "FIT_DEFINITION_INVALID",
          `architecture byte 0x${hex2(arch)} is neither little- nor big-endian`,
          p + 1,
          "structural",
        );
        const r = resync(pos, "FIT_DEFINITION_INVALID");
        pos = r.next;
        resyncs += 1;
        yield r.skip;
        continue;
      }
      const big = arch === 1;
      const globalNum = view.getUint16(p + 2, !big);
      const nf = u8(data, p + 4);
      p += 5;
      if (p + nf * 3 > end) {
        yield defectEvent(
          "FIT_TRUNCATED",
          "file ends inside a definition's field list",
          pos,
          "structural",
        );
        stopped = true;
        break;
      }
      const fields: FieldSpec[] = [];
      for (let i = 0; i < nf; i++) {
        fields.push({
          num: u8(data, p + i * 3),
          size: u8(data, p + i * 3 + 1),
          baseType: u8(data, p + i * 3 + 2),
        });
      }
      p += nf * 3;
      const devFields: DevFieldSpec[] = [];
      if (hasDev) {
        if (p + 1 > end) {
          yield defectEvent(
            "FIT_TRUNCATED",
            "file ends before the developer-field count byte",
            pos,
            "structural",
          );
          stopped = true;
          break;
        }
        const nd = u8(data, p);
        p += 1;
        if (p + nd * 3 > end) {
          yield defectEvent(
            "FIT_TRUNCATED",
            "file ends inside a definition's developer-field list",
            pos,
            "structural",
          );
          stopped = true;
          break;
        }
        for (let i = 0; i < nd; i++) {
          devFields.push({
            num: u8(data, p + i * 3),
            size: u8(data, p + i * 3 + 1),
            devDataIndex: u8(data, p + i * 3 + 2),
          });
        }
        p += nd * 3;
      }
      const frame: DefinitionFrame = {
        kind: "definition",
        offset: pos,
        localId: local,
        globalNum,
        bigEndian: big,
        fields,
        devFields,
      };
      localDefs.set(local, frame); // redefinition is legal and common (taxonomy #20)
      localSizes.set(local, payloadSize(frame));
      yield frame;
      pos = p;
    } else {
      // normal data message
      const local = hdr & 0x0f;
      const df = localDefs.get(local);
      if (df === undefined) {
        yield defectEvent(
          "FIT_UNDEFINED_LOCAL_TYPE",
          `data message references undefined local type ${local}`,
          pos,
          "structural",
        );
        const r = resync(pos, "FIT_UNDEFINED_LOCAL_TYPE");
        pos = r.next;
        resyncs += 1;
        yield r.skip;
        continue;
      }
      const size = localSizes.get(local) as number;
      if (pos + 1 + size > end) {
        yield defectEvent(
          "FIT_TRUNCATED",
          `record at byte ${pos} needs ${size} payload bytes; only ${end - pos - 1} remain`,
          pos,
          "structural",
        );
        stopped = true;
        break;
      }
      yield {
        kind: "data",
        offset: pos,
        localId: local,
        definition: df,
        payload: data.subarray(pos + 1, pos + 1 + size),
        timeOffset: null,
      };
      pos += 1 + size;
    }
  }

  if (stopped) {
    // Truncation only: the bytes simply end; nothing to resynchronize into.
    yield { kind: "eos", consumed: n };
    return;
  }

  if (truncatedDeclared) {
    yield defectEvent(
      "FIT_TRUNCATED",
      `header declares ${dataSize} data bytes; only ${n - bodyStart} are present`,
      n,
      "structural",
    );
    yield { kind: "eos", consumed: n };
    return;
  }

  if (end + 2 <= n) {
    const declaredCrc = view.getUint16(end, true);
    const computed = crc16(data.subarray(start, end));
    const ok = declaredCrc === computed;
    if (!ok) {
      let why: string;
      if (declaredCrc === 0) {
        why = "trailer is 0x0000: unterminated-write class";
      } else if (resyncs || stopped) {
        why = "stream also had structural damage: storage corruption class";
      } else {
        why =
          "content decodes cleanly: in-place corruption or encoder CRC laziness (fitparse #9 class)";
      }
      yield defectEvent(
        "FIT_CRC_MISMATCH",
        `file CRC 0x${hex4(declaredCrc)} != computed 0x${hex4(computed)} (${why})`,
        end,
        "structural",
      );
    }
    yield { kind: "crc", offset: end, declared: declaredCrc, computed, ok };
    yield { kind: "eos", consumed: end + 2 };
  } else {
    yield defectEvent(
      "FIT_CRC_MISSING",
      "no room for the 2-byte file CRC after the data",
      end,
      "structural",
    );
    yield { kind: "eos", consumed: n };
  }
}

/** Python's `f"0x{v:04X}"` body. Kept local so the message strings match exactly. */
function hex4(v: number): string {
  return v.toString(16).toUpperCase().padStart(4, "0");
}

function hex2(v: number): string {
  return v.toString(16).toUpperCase().padStart(2, "0");
}
