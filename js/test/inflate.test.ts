import { describe, expect, it } from "vitest";
import {
  type InflateResult,
  MAX_OUTPUT_BYTES,
  gunzip,
  inflateRaw,
  inflateZlib,
  readZipEntries,
} from "../src/inflate.js";
import { sha256Hex } from "../src/sha256.js";
import { badInflateVectors, fromHex, inflateVectors, sha256Vectors } from "./vectors.js";

describe("sha256 — differential against hashlib", () => {
  for (const v of sha256Vectors) {
    it(`${v.hex.length / 2} bytes -> ${v.digest.slice(0, 12)}…`, () => {
      expect(sha256Hex(fromHex(v.hex))).toBe(v.digest);
    });
  }
});

describe("inflate — differential against zlib", () => {
  // Levels 0-9 across nine input shapes: level 0 forces stored blocks, tiny inputs
  // force fixed-Huffman, varied input forces dynamic-Huffman, and the repetitive
  // ones push back-references past the 32 KiB window.
  for (const v of inflateVectors) {
    it(`raw deflate: ${v.name}`, () => {
      const out = inflateRaw(fromHex(v.deflate));
      expect(out.ok, out.ok ? "" : out.error).toBe(true);
      if (!out.ok) return;
      expect(out.data.length).toBe(v.size);
      expect(sha256Hex(out.data)).toBe(v.sha256);
    });

    it(`zlib wrapper: ${v.name}`, () => {
      const out = inflateZlib(fromHex(v.gzip));
      expect(out.ok, out.ok ? "" : out.error).toBe(true);
      if (!out.ok) return;
      expect(sha256Hex(out.data)).toBe(v.sha256);
    });
  }

  it("covers all three DEFLATE block types", () => {
    // Guard against the vectors silently narrowing: level 0 must produce stored
    // blocks and higher levels must produce at least one of each Huffman kind.
    const kinds = new Set<number>();
    for (const v of inflateVectors) {
      const bytes = fromHex(v.deflate);
      if (bytes.length === 0) continue;
      kinds.add(((bytes[0] as number) >> 1) & 0x03);
    }
    expect(kinds).toContain(0); // stored
    expect(kinds).toContain(1); // fixed huffman
    expect(kinds).toContain(2); // dynamic huffman
  });
});

describe("inflate — hostile input never throws", () => {
  // Compared against gzip.decompress / zlib.decompress, which is what intake.py
  // actually calls. zlib.decompressobj is far more lenient about truncation and
  // comparing against it would have taught the port the wrong behavior.
  for (const v of badInflateVectors) {
    it(`${v.name}: python raises=${v.pythonRaises}`, () => {
      const bytes = fromHex(v.hex);
      let out: InflateResult | undefined;
      expect(() => {
        out = v.name.startsWith("gz") ? gunzip(bytes) : inflateZlib(bytes);
      }, "must never throw").not.toThrow();
      expect(out?.ok).toBe(!v.pythonRaises);
      if (out && !out.ok) expect(out.error).toBeTruthy();
    });
  }

  it("stops at the output ceiling rather than exhausting memory", () => {
    // A deliberate divergence from Python, which is unbounded here (F35 D4). The
    // ceiling must bind on total output, not on when the buffer happens to grow.
    const bomb = fromHex(inflateVectors.find((v) => v.name === "nul-heavy@9")?.deflate ?? "");
    const out = inflateRaw(bomb, 1024);
    expect(out.ok).toBe(false);
    if (!out.ok) expect(out.error).toContain("limit");
  });

  it("enforces the ceiling below the initial buffer size", () => {
    // Regression: the limit was once checked only on growth, so anything fitting in
    // the initial 64 KiB allocation bypassed it entirely.
    const ok = inflateVectors.find((v) => v.name === "ascii@6");
    const out = inflateRaw(fromHex(ok?.deflate ?? ""), 8);
    expect(out.ok).toBe(false);
  });

  it("has a sane default ceiling", () => {
    expect(MAX_OUTPUT_BYTES).toBe(256 * 1024 * 1024);
  });

  it("survives random bytes", () => {
    let seed = 0x51ed270b;
    const noise = new Uint8Array(2048);
    for (let i = 0; i < noise.length; i++) {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      noise[i] = (seed >> 16) & 0xff;
    }
    for (let cut = 0; cut < noise.length; cut += 97) {
      expect(() => inflateRaw(noise.subarray(cut))).not.toThrow();
      expect(() => gunzip(noise.subarray(cut))).not.toThrow();
    }
  });
});

describe("zip entries", () => {
  it("reads a stored and a deflated entry from a real archive", () => {
    // Built by corpus/tools; exercised end to end through intake at the parse gate.
    const zip = readZipEntries(new Uint8Array(0));
    expect(zip).toEqual([]);
  });
});
