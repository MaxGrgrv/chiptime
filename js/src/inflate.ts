/**
 * DEFLATE (RFC 1951), gzip (RFC 1952) and the ZIP subset needed to reach `.fit`
 * entries.
 *
 * The one module in this package with **no Python twin**: CPython has `gzip` and
 * `zipfile` in its standard library, and JavaScript has neither synchronously.
 * Three constraints intersect and force this to be written rather than borrowed:
 * zero runtime dependencies, a synchronous `parse()`, and browser support.
 * `node:zlib` fails the third, `DecompressionStream` the second, a dependency the
 * first (ADR-0009 section 7).
 *
 * Because it has no reference implementation to diff against, it is covered by
 * vectors generated from CPython's `zlib`/`gzip` across all three DEFLATE block
 * types, back-references crossing the 32 KiB window, every compression level, and
 * corrupt input (F35 spec, amendment D3).
 *
 * Nothing here throws on malformed input: every failure is a typed result, the same
 * contract the frame reader carries (ADR-0003).
 */

export type InflateResult =
  | { readonly ok: true; readonly data: Uint8Array }
  | { readonly ok: false; readonly error: string };

/**
 * Output ceiling, ~256 MiB.
 *
 * A **deliberate divergence** from Python, which is unbounded here —
 * `gzip.decompress` reads to EOF and fails by `MemoryError`. So a bomb that Python
 * merely dies on, this rejects cleanly. The runtime is the reason: a malicious file
 * that kills a Node process is bad, and one that kills a browser tab is worse. No
 * corpus case exercises it (F35 spec, amendment D4).
 */
export const MAX_OUTPUT_BYTES = 256 * 1024 * 1024;

const LENGTH_BASE = [
  3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131,
  163, 195, 227, 258,
];
const LENGTH_EXTRA = [
  0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0,
];
const DIST_BASE = [
  1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537, 2049,
  3073, 4097, 6145, 8193, 12289, 16385, 24577,
];
const DIST_EXTRA = [
  0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13,
];
const CRC32_TABLE = (() => {
  const table = new Int32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[i] = c;
  }
  return table;
})();

/** CRC-32 (IEEE), as gzip's trailer requires. */
export function crc32(data: Uint8Array): number {
  let c = 0xffffffff;
  for (const b of data) c = (CRC32_TABLE[(c ^ b) & 0xff] as number) ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

const CLEN_ORDER = [16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15];

/** A canonical Huffman table: `counts[len]` and the symbols in code order. */
interface Huffman {
  readonly counts: Int32Array;
  readonly symbols: Int32Array;
}

function buildHuffman(lengths: Uint8Array, n: number): Huffman | null {
  const counts = new Int32Array(16);
  for (let i = 0; i < n; i++) {
    const l = lengths[i] as number;
    counts[l] = (counts[l] as number) + 1;
  }
  counts[0] = 0;
  // Over-subscribed or incomplete codes are corruption, not something to guess at.
  let left = 1;
  for (let len = 1; len < 16; len++) {
    left <<= 1;
    left -= counts[len] as number;
    if (left < 0) return null;
  }
  const offsets = new Int32Array(16);
  for (let len = 1; len < 15; len++) {
    offsets[len + 1] = (offsets[len] as number) + (counts[len] as number);
  }
  const symbols = new Int32Array(n);
  for (let sym = 0; sym < n; sym++) {
    const l = lengths[sym] as number;
    if (l === 0) continue;
    const at = offsets[l] as number;
    symbols[at] = sym;
    offsets[l] = at + 1;
  }
  return { counts, symbols };
}

/** LSB-first bit reader over the compressed stream. */
class BitReader {
  pos = 0;
  private bitBuf = 0;
  private bitCnt = 0;
  overrun = false;

  constructor(private readonly data: Uint8Array) {}

  bits(need: number): number {
    while (this.bitCnt < need) {
      if (this.pos >= this.data.length) {
        this.overrun = true;
        return -1;
      }
      this.bitBuf |= (this.data[this.pos++] as number) << this.bitCnt;
      this.bitCnt += 8;
    }
    const out = this.bitBuf & ((1 << need) - 1);
    this.bitBuf >>>= need;
    this.bitCnt -= need;
    return out;
  }

  alignToByte(): void {
    this.bitBuf = 0;
    this.bitCnt = 0;
  }

  decode(h: Huffman): number {
    let code = 0;
    let first = 0;
    let index = 0;
    for (let len = 1; len < 16; len++) {
      const b = this.bits(1);
      if (b < 0) return -1;
      code |= b;
      const count = h.counts[len] as number;
      if (code - first < count) return h.symbols[index + (code - first)] as number;
      index += count;
      first = (first + count) << 1;
      code <<= 1;
    }
    return -1;
  }
}

/** Growable output buffer with a hard ceiling. */
class Sink {
  private buf = new Uint8Array(1 << 16);
  len = 0;

  constructor(private readonly limit: number) {}

  private ensure(extra: number): boolean {
    // The limit is checked first, unconditionally. Checking it only on growth let
    // anything fitting in the initial allocation through, which made the ceiling a
    // function of the starting buffer size rather than of the limit.
    if (this.len + extra > this.limit) return false;
    if (this.len + extra <= this.buf.length) return true;
    let size = this.buf.length * 2;
    while (size < this.len + extra) size *= 2;
    const next = new Uint8Array(Math.min(size, this.limit));
    next.set(this.buf.subarray(0, this.len));
    this.buf = next;
    return true;
  }

  push(byte: number): boolean {
    if (!this.ensure(1)) return false;
    this.buf[this.len++] = byte;
    return true;
  }

  copyFrom(distance: number, length: number): boolean {
    if (distance > this.len || distance <= 0) return false;
    if (!this.ensure(length)) return false;
    let from = this.len - distance;
    for (let i = 0; i < length; i++) this.buf[this.len++] = this.buf[from++] as number;
    return true;
  }

  append(bytes: Uint8Array): boolean {
    if (!this.ensure(bytes.length)) return false;
    this.buf.set(bytes, this.len);
    this.len += bytes.length;
    return true;
  }

  result(): Uint8Array {
    return this.buf.slice(0, this.len);
  }
}

let FIXED_LIT: Huffman | null = null;
let FIXED_DIST: Huffman | null = null;

function fixedTables(): [Huffman, Huffman] {
  if (FIXED_LIT === null || FIXED_DIST === null) {
    const lit = new Uint8Array(288);
    lit.fill(8, 0, 144);
    lit.fill(9, 144, 256);
    lit.fill(7, 256, 280);
    lit.fill(8, 280, 288);
    const dist = new Uint8Array(30).fill(5);
    FIXED_LIT = buildHuffman(lit, 288) as Huffman;
    FIXED_DIST = buildHuffman(dist, 30) as Huffman;
  }
  return [FIXED_LIT, FIXED_DIST];
}

/** Raw DEFLATE (RFC 1951). `consumed` reports how far into `data` the stream ran. */
export function inflateRaw(
  data: Uint8Array,
  limit: number = MAX_OUTPUT_BYTES,
): InflateResult & { consumed?: number } {
  const br = new BitReader(data);
  const sink = new Sink(limit);

  for (;;) {
    const final = br.bits(1);
    const type = br.bits(2);
    if (final < 0 || type < 0) return { ok: false, error: "truncated deflate stream" };

    if (type === 0) {
      br.alignToByte();
      if (br.pos + 4 > data.length) return { ok: false, error: "truncated stored block header" };
      const len = (data[br.pos] as number) | ((data[br.pos + 1] as number) << 8);
      const nlen = (data[br.pos + 2] as number) | ((data[br.pos + 3] as number) << 8);
      br.pos += 4;
      if ((len ^ 0xffff) !== nlen) return { ok: false, error: "stored block length check failed" };
      if (br.pos + len > data.length) return { ok: false, error: "truncated stored block" };
      if (!sink.append(data.subarray(br.pos, br.pos + len))) {
        return { ok: false, error: "output exceeds the size limit" };
      }
      br.pos += len;
    } else if (type === 1 || type === 2) {
      let lit: Huffman;
      let dist: Huffman;
      if (type === 1) {
        [lit, dist] = fixedTables();
      } else {
        const hlit = br.bits(5);
        const hdist = br.bits(5);
        const hclen = br.bits(4);
        if (hlit < 0 || hdist < 0 || hclen < 0) {
          return { ok: false, error: "truncated dynamic block header" };
        }
        const nlit = hlit + 257;
        const ndist = hdist + 1;
        const nclen = hclen + 4;
        const clenLengths = new Uint8Array(19);
        for (let i = 0; i < nclen; i++) {
          const v = br.bits(3);
          if (v < 0) return { ok: false, error: "truncated code-length alphabet" };
          clenLengths[CLEN_ORDER[i] as number] = v;
        }
        const clenTable = buildHuffman(clenLengths, 19);
        if (clenTable === null) return { ok: false, error: "invalid code-length alphabet" };

        const lengths = new Uint8Array(nlit + ndist);
        let i = 0;
        while (i < nlit + ndist) {
          const sym = br.decode(clenTable);
          if (sym < 0) return { ok: false, error: "truncated code-length sequence" };
          if (sym < 16) {
            lengths[i++] = sym;
          } else if (sym === 16) {
            if (i === 0) return { ok: false, error: "code-length repeat with no previous length" };
            const prev = lengths[i - 1] as number;
            const rep = br.bits(2);
            if (rep < 0) return { ok: false, error: "truncated code-length repeat" };
            for (let r = 0; r < rep + 3 && i < lengths.length; r++) lengths[i++] = prev;
          } else if (sym === 17) {
            const rep = br.bits(3);
            if (rep < 0) return { ok: false, error: "truncated code-length repeat" };
            i += rep + 3;
          } else {
            const rep = br.bits(7);
            if (rep < 0) return { ok: false, error: "truncated code-length repeat" };
            i += rep + 11;
          }
        }
        if (i > nlit + ndist) return { ok: false, error: "code-length sequence overruns" };
        const litTable = buildHuffman(lengths.subarray(0, nlit), nlit);
        const distTable = buildHuffman(lengths.subarray(nlit), ndist);
        if (litTable === null || distTable === null) {
          return { ok: false, error: "invalid huffman table" };
        }
        lit = litTable;
        dist = distTable;
      }

      for (;;) {
        const sym = br.decode(lit);
        if (sym < 0) return { ok: false, error: "truncated compressed block" };
        if (sym < 256) {
          if (!sink.push(sym)) return { ok: false, error: "output exceeds the size limit" };
          continue;
        }
        if (sym === 256) break;
        const li = sym - 257;
        if (li >= LENGTH_BASE.length) return { ok: false, error: "invalid length symbol" };
        const extraLen = br.bits(LENGTH_EXTRA[li] as number);
        if (extraLen < 0) return { ok: false, error: "truncated length extra bits" };
        const length = (LENGTH_BASE[li] as number) + extraLen;
        const dsym = br.decode(dist);
        if (dsym < 0 || dsym >= DIST_BASE.length)
          return { ok: false, error: "invalid distance symbol" };
        const extraDist = br.bits(DIST_EXTRA[dsym] as number);
        if (extraDist < 0) return { ok: false, error: "truncated distance extra bits" };
        const distance = (DIST_BASE[dsym] as number) + extraDist;
        if (!sink.copyFrom(distance, length)) {
          return { ok: false, error: "back-reference before the start of output, or size limit" };
        }
      }
    } else {
      return { ok: false, error: "reserved deflate block type" };
    }
    if (final === 1) break;
  }
  return { ok: true, data: sink.result(), consumed: br.pos };
}

/** gzip (RFC 1952). */
export function gunzip(data: Uint8Array, limit: number = MAX_OUTPUT_BYTES): InflateResult {
  // CPython's gzip.decompress(b"") returns b"" rather than raising; matched here so
  // the module agrees with the API intake actually calls.
  if (data.length === 0) return { ok: true, data: new Uint8Array(0) };
  if (data.length < 18) return { ok: false, error: "gzip stream too short" };
  if (data[0] !== 0x1f || data[1] !== 0x8b) return { ok: false, error: "bad gzip magic" };
  const method = data[2] as number;
  if (method !== 8) return { ok: false, error: `unsupported gzip method ${method}` };
  const flg = data[3] as number;
  let p = 10;
  if (flg & 0x04) {
    // FEXTRA
    if (p + 2 > data.length) return { ok: false, error: "truncated gzip extra field" };
    const xlen = (data[p] as number) | ((data[p + 1] as number) << 8);
    p += 2 + xlen;
  }
  if (flg & 0x08) {
    // FNAME
    while (p < data.length && data[p] !== 0) p++;
    p++;
  }
  if (flg & 0x10) {
    // FCOMMENT
    while (p < data.length && data[p] !== 0) p++;
    p++;
  }
  if (flg & 0x02) p += 2; // FHCRC
  if (p >= data.length) return { ok: false, error: "truncated gzip header" };
  const out = inflateRaw(data.subarray(p), limit);
  if (!out.ok) return out;

  // The trailer is not optional. Python's gzip.decompress validates CRC-32 and
  // ISIZE, so skipping them here would accept corrupt bodies it rejects -- which is
  // precisely what the corrupt-stream vectors caught.
  const end = p + (out.consumed ?? 0);
  if (end + 8 > data.length) return { ok: false, error: "truncated gzip trailer" };
  const trailer = new DataView(data.buffer, data.byteOffset + end, 8);
  const wantCrc = trailer.getUint32(0, true);
  const wantSize = trailer.getUint32(4, true);
  if (crc32(out.data) !== wantCrc) return { ok: false, error: "gzip CRC-32 mismatch" };
  if (out.data.length >>> 0 !== wantSize) return { ok: false, error: "gzip ISIZE mismatch" };
  return { ok: true, data: out.data };
}

/** zlib wrapper (RFC 1950), for completeness — ZIP entries use raw deflate. */
export function inflateZlib(data: Uint8Array, limit: number = MAX_OUTPUT_BYTES): InflateResult {
  if (data.length < 2) return { ok: false, error: "zlib stream too short" };
  const cmf = data[0] as number;
  const flg = data[1] as number;
  if ((cmf & 0x0f) !== 8) return { ok: false, error: "unsupported zlib method" };
  if (((cmf << 8) | flg) % 31 !== 0) return { ok: false, error: "zlib header check failed" };
  if (flg & 0x20) return { ok: false, error: "zlib preset dictionary unsupported" };
  const out = inflateRaw(data.subarray(2), limit);
  if (!out.ok) return out;
  const end = 2 + (out.consumed ?? 0);
  if (end + 4 > data.length) return { ok: false, error: "truncated zlib adler-32" };
  const want = new DataView(data.buffer, data.byteOffset + end, 4).getUint32(0, false);
  if (adler32(out.data) !== want) return { ok: false, error: "zlib adler-32 mismatch" };
  return { ok: true, data: out.data };
}

/** Adler-32, as zlib's trailer requires. */
export function adler32(data: Uint8Array): number {
  let a = 1;
  let b = 0;
  for (const byte of data) {
    a = (a + byte) % 65521;
    b = (b + a) % 65521;
  }
  return ((b << 16) | a) >>> 0;
}

export interface ZipEntry {
  readonly name: string;
  readonly data: Uint8Array;
}

const UTF8_DECODER = new TextDecoder("utf-8");

/**
 * Read ZIP entries by walking local file headers.
 *
 * The central directory is the canonical index, but a truncated archive often keeps
 * readable local headers after the directory is gone — and salvaging what is there
 * is this library's whole posture. Entries whose data cannot be read are skipped
 * rather than aborting the archive.
 */
export function readZipEntries(data: Uint8Array, limit: number = MAX_OUTPUT_BYTES): ZipEntry[] {
  const entries: ZipEntry[] = [];
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  let p = 0;
  while (p + 30 <= data.length) {
    if (view.getUint32(p, true) !== 0x04034b50) break;
    const flags = view.getUint16(p + 6, true);
    const method = view.getUint16(p + 8, true);
    let compSize = view.getUint32(p + 18, true);
    const nameLen = view.getUint16(p + 26, true);
    const extraLen = view.getUint16(p + 28, true);
    const nameStart = p + 30;
    const dataStart = nameStart + nameLen + extraLen;
    if (dataStart > data.length) break;
    const name = UTF8_DECODER.decode(data.subarray(nameStart, nameStart + nameLen));

    if (flags & 0x08 && compSize === 0) {
      // Sizes live in a trailing data descriptor. Inflating tells us where the
      // stream ended, which is the only way to find the next header.
      if (method === 8) {
        const out = inflateRaw(data.subarray(dataStart), limit);
        if (out.ok) {
          entries.push({ name, data: out.data });
          compSize = out.consumed ?? 0;
          p = dataStart + compSize;
          // Skip the data descriptor (optional signature + 12 bytes).
          if (p + 4 <= data.length && view.getUint32(p, true) === 0x08074b50) p += 4;
          p += 12;
          continue;
        }
      }
      break;
    }

    const body = data.subarray(dataStart, dataStart + compSize);
    if (method === 0) {
      entries.push({ name, data: body });
    } else if (method === 8) {
      const out = inflateRaw(body, limit);
      if (out.ok) entries.push({ name, data: out.data });
    }
    p = dataStart + compSize;
  }
  return entries;
}
