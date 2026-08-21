import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { iterFrames } from "../src/api.js";
import {
  CrcMismatchError,
  EmptyFileError,
  FitError,
  HeaderError,
  NotFitError,
  ProtocolError,
  TruncatedError,
  defectToError,
} from "../src/errors.js";
import { type FrameEvent, crc16, readStream } from "../src/frames.js";
import { crcVectors, fromHex } from "./vectors.js";

const CORPUS = fileURLToPath(new URL("../../corpus/cases/", import.meta.url));
const rideSmooth = new Uint8Array(readFileSync(`${CORPUS}clean/ride-smooth/input.fit`));

describe("crc16 — differential against CPython", () => {
  for (const [i, v] of crcVectors.entries()) {
    it(`vector ${i} (${v.hex.length / 2} bytes) -> ${v.crc}`, () => {
      expect(crc16(fromHex(v.hex), v.seed ?? 0)).toBe(v.crc);
    });
  }

  it("chains like the seeded Python call", () => {
    const abc = fromHex("616263");
    const xyz = fromHex("78797a");
    expect(crc16(abc, crc16(xyz))).toBe(crc16(new Uint8Array([...xyz, ...abc])));
  });
});

describe("FitError hierarchy", () => {
  const cases: [new (c: string, d: string) => FitError, string][] = [
    [NotFitError, "NotFitError"],
    [EmptyFileError, "EmptyFileError"],
    [HeaderError, "HeaderError"],
    [TruncatedError, "TruncatedError"],
    [CrcMismatchError, "CrcMismatchError"],
    [ProtocolError, "ProtocolError"],
  ];

  for (const [Cls, name] of cases) {
    it(`${name} satisfies instanceof, for itself and for FitError and Error`, () => {
      // Subclassing Error severs the prototype chain on downlevel targets. A
      // hierarchy that silently fails to match is worse than none, because callers
      // write the check and believe it.
      const err = new Cls("SOME_CODE", "some detail");
      expect(err instanceof Cls).toBe(true);
      expect(err instanceof FitError).toBe(true);
      expect(err instanceof Error).toBe(true);
      expect(err.name).toBe(name);
    });
  }

  it("formats the message the way Python does", () => {
    expect(new FitError("FIT_TRUNCATED", "file ends mid-record").message).toBe(
      "FIT_TRUNCATED: file ends mid-record",
    );
    expect(
      new FitError("FIT_TRUNCATED", "file ends mid-record", { suggestion: "use lenient" }).message,
    ).toBe("FIT_TRUNCATED: file ends mid-record — use lenient");
  });

  it("maps defects to the class Python maps them to", () => {
    const d = { code: "FIT_TRUNCATED", detail: "d", offset: 12, severity: "structural" } as const;
    const err = defectToError(d);
    expect(err).toBeInstanceOf(TruncatedError);
    expect(err.code).toBe("FIT_TRUNCATED");
    expect(err.byteOffset).toBe(12);
  });

  it("falls back to ProtocolError for an unmapped code, as Python does", () => {
    const d = { code: "NO_SUCH_CODE", detail: "d", offset: 0, severity: "data" } as const;
    expect(defectToError(d)).toBeInstanceOf(ProtocolError);
  });
});

describe("iterFrames", () => {
  it("reads a clean file end to end", () => {
    const events = [...iterFrames(rideSmooth)];
    expect(events[0]?.kind).toBe("header");
    expect(events.at(-1)?.kind).toBe("eos");
    expect(events.filter((e) => e.kind === "defect")).toHaveLength(0);
    expect(events.filter((e) => e.kind === "data").length).toBeGreaterThan(0);
  });

  it("yields nothing at all for an empty input", () => {
    // The chain loop never runs, so readStream's FIT_EMPTY is never reached.
    // Reporting an empty file is parse()'s job (taxonomy #1), not the frame layer's.
    expect([...iterFrames(new Uint8Array(0))]).toEqual([]);
    expect([...readStream(new Uint8Array(0))].map((e) => e.kind)).toEqual(["defect", "eos"]);
  });

  it("continues into a chained second stream (taxonomy #12)", () => {
    const chained = new Uint8Array(
      readFileSync(`${CORPUS}structural/chained-two-activities/input.fit`),
    );
    const headers = [...iterFrames(chained)].filter((e) => e.kind === "header");
    expect(headers.length).toBe(2);
  });

  it("raises in strict mode with a code and a suggestion", () => {
    const truncated = rideSmooth.subarray(0, rideSmooth.length - 40);
    expect(() => [...iterFrames(truncated, { mode: "strict" })]).toThrow(FitError);
    try {
      [...iterFrames(truncated, { mode: "strict" })];
      expect.unreachable("strict mode should have raised");
    } catch (e) {
      const err = e as FitError;
      expect(err.code).toBeTruthy();
      expect(err.suggestion).toContain("lenient");
    }
  });

  it("collects rather than raises in lenient mode", () => {
    const truncated = rideSmooth.subarray(0, rideSmooth.length - 40);
    const events = [...iterFrames(truncated)];
    expect(events.some((e) => e.kind === "defect")).toBe(true);
  });
});

describe("hostile input — the module's design promise", () => {
  // PRD §6.1: this reader is incapable of crashing on content. The Python side has
  // the same sweep; a DataView read past the end throws RangeError, so this is
  // testing that every bounds check is actually there.
  it("never throws on a truncation sweep over a clean file", () => {
    for (let cut = 0; cut <= rideSmooth.length; cut++) {
      const slice = rideSmooth.subarray(0, cut);
      expect(() => {
        for (const _ of iterFrames(slice)) {
          // drain
        }
      }, `throw at cut ${cut}`).not.toThrow();
    }
  });

  it("accounts for every byte on a truncation sweep", () => {
    for (let cut = 12; cut <= rideSmooth.length; cut += 7) {
      const events = [...iterFrames(rideSmooth.subarray(0, cut))] as FrameEvent[];
      const eos = events.filter((e) => e.kind === "eos");
      expect(eos.length, `no EndOfStream at cut ${cut}`).toBeGreaterThan(0);
      const last = eos.at(-1);
      if (last?.kind === "eos") expect(last.consumed).toBeLessThanOrEqual(cut);
    }
  });

  it("terminates on random bytes rather than hunting forever", () => {
    // Deterministic pseudo-random: a fixed LCG, so a failure reproduces exactly.
    let seed = 0x2f6e2b1;
    const noise = new Uint8Array(4096);
    for (let i = 0; i < noise.length; i++) {
      seed = (seed * 1103515245 + 12345) & 0x7fffffff;
      noise[i] = (seed >> 16) & 0xff;
    }
    expect(() => [...iterFrames(noise)]).not.toThrow();
    // A header-shaped prefix followed by noise is the resync scanner's worst case.
    const withHeader = new Uint8Array(noise);
    withHeader.set(rideSmooth.subarray(0, 14), 0);
    expect(() => [...iterFrames(withHeader)]).not.toThrow();
  });

  it("never throws on any corpus case", () => {
    const glob = [
      "clean/ride-smooth",
      "structural/preamble-garbage",
      "protocol/frame-shift-insert",
    ];
    for (const name of glob) {
      const data = new Uint8Array(readFileSync(`${CORPUS}${name}/input.fit`));
      expect(() => [...iterFrames(data)], name).not.toThrow();
    }
  });
});
