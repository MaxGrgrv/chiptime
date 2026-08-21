import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { iterMessages } from "../src/api.js";
import {
  Decoder,
  civilFromUnix,
  fitTsToIso,
  fitTsToIsoLocal,
  sanitizeFieldName,
} from "../src/decode.js";
import type { DataFrame, DefinitionFrame } from "../src/frames.js";
import { fromHex, timestampVectors, utf8Vectors } from "./vectors.js";

const CORPUS = fileURLToPath(new URL("../../corpus/cases/", import.meta.url));
const rideSmooth = new Uint8Array(readFileSync(`${CORPUS}clean/ride-smooth/input.fit`));

/** Build a synthetic definition + data frame, for paths the corpus does not reach. */
function synth(
  globalNum: number,
  fields: { num: number; size: number; baseType: number }[],
  payload: number[],
  opts: { offset?: number; bigEndian?: boolean; timeOffset?: number | null } = {},
): DataFrame {
  const definition: DefinitionFrame = {
    kind: "definition",
    offset: opts.offset ?? 0,
    localId: 0,
    globalNum,
    bigEndian: opts.bigEndian ?? false,
    fields,
    devFields: [],
  };
  return {
    kind: "data",
    offset: (opts.offset ?? 0) + 1,
    localId: 0,
    definition,
    payload: new Uint8Array(payload),
    timeOffset: opts.timeOffset ?? null,
  };
}

describe("timestamps — differential against CPython", () => {
  for (const v of timestampVectors) {
    it(`fitTsToIso(${v.fit}) === ${v.iso}`, () => {
      expect(fitTsToIso(v.fit)).toBe(v.iso);
      expect(fitTsToIsoLocal(v.fit)).toBe(v.local);
    });
  }

  it("uses integer arithmetic, not Date", () => {
    // Date.toISOString() would append ".000"; the Python formatter does not, which
    // is the whole reason Date is banned in js/src (ADR-0009 §5).
    expect(fitTsToIso(1149238800)).not.toContain(".");
    expect(civilFromUnix(0)).toEqual([1970, 1, 1, 0, 0, 0]);
    expect(civilFromUnix(-1)).toEqual([1969, 12, 31, 23, 59, 59]);
    expect(civilFromUnix(951782400)).toEqual([2000, 2, 29, 0, 0, 0]); // leap day
  });
});

describe("UTF-8 decoding — differential against CPython", () => {
  for (const [i, v] of utf8Vectors.entries()) {
    it(`vector ${i} (${v.hex || "empty"})`, () => {
      // Exercised through a synthetic string field, so the test covers the decoder's
      // own segmentation rather than TextDecoder in isolation.
      const bytes = fromHex(v.hex);
      const dec = new Decoder();
      const msg = dec.decode(
        synth(
          0xffff,
          [{ num: 0, size: bytes.length || 1, baseType: 0x07 }],
          [...(bytes.length ? bytes : [0])],
        ),
      );
      expect(msg.fields.get("field_0")?.value ?? null).toEqual(v.value);
    });
  }
});

describe("sanitizeFieldName", () => {
  it("matches Python's [^a-z0-9]+ collapsing", () => {
    expect(sanitizeFieldName("Leg Spring Stiffness")).toBe("leg_spring_stiffness");
    expect(sanitizeFieldName("  Form Power  ")).toBe("form_power");
    expect(sanitizeFieldName("SmO2%")).toBe("smo2");
    expect(sanitizeFieldName("a--b__c")).toBe("a_b_c");
    expect(sanitizeFieldName("!!!")).toBe("");
    expect(sanitizeFieldName("Core Temp (°C)")).toBe("core_temp_c");
  });
});

describe("contract #4 — sentinels resolve before scaling", () => {
  // The corpus does not cover this: a mutation moving the sentinel check after the
  // enum branch passed all 72 cases. Covered here explicitly because getting it
  // backwards produces *believable* numbers — 65535/100 reads like a real value.
  it("nulls a sentinel on a scaled field rather than scaling it", () => {
    const dec = new Decoder();
    // record.altitude: uint16, scale 5, offset 500. 0xFFFF is the sentinel.
    const msg = dec.decode(synth(20, [{ num: 2, size: 2, baseType: 0x84 }], [0xff, 0xff]));
    expect(msg.fields.get("altitude")?.value).toBeNull();
    expect(msg.fields.get("altitude")?.raw).toBe(0xffff);
  });

  it("nulls a sentinel on an enum field rather than mapping it", () => {
    const dec = new Decoder();
    // session.sport is an enum; 0xFF is the uint8 sentinel.
    const msg = dec.decode(synth(18, [{ num: 5, size: 1, baseType: 0x00 }], [0xff]));
    expect(msg.fields.get("sport")?.value).toBeNull();
  });

  it("keeps a real zero as zero", () => {
    const dec = new Decoder();
    const msg = dec.decode(synth(20, [{ num: 7, size: 2, baseType: 0x84 }], [0x00, 0x00]));
    expect(msg.fields.get("power")?.value).toBe(0);
    expect(msg.fields.get("power")?.value).not.toBeNull();
  });

  it("scales and offsets a real value", () => {
    const dec = new Decoder();
    // altitude raw 3000 -> 3000/5 - 500 = 100 m
    const msg = dec.decode(synth(20, [{ num: 2, size: 2, baseType: 0x84 }], [0xb8, 0x0b]));
    expect(msg.fields.get("altitude")?.value).toBeCloseTo(100, 10);
  });
});

describe("64-bit fields — the bigint boundary (amendment C3)", () => {
  it("decodes a uint64 field as bigint without precision loss", () => {
    const dec = new Decoder();
    const bytes = [0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0x0f]; // 0x0fffffffffffffff
    const msg = dec.decode(synth(0xffff, [{ num: 0, size: 8, baseType: 0x8f }], bytes));
    expect(msg.fields.get("field_0")?.raw).toBe(0x0fffffffffffffffn);
  });

  it("does not throw when a SCALED field is declared as uint64", () => {
    // The corpus exercises one 64-bit case and it carries no scale. Base types are
    // declared per definition frame, so any of the 419 scaled profile fields could
    // arrive this way from a real encoder — mixed bigint/number arithmetic would
    // throw in a user's file rather than here.
    const dec = new Decoder();
    const bytes = [0x10, 0x27, 0, 0, 0, 0, 0, 0]; // 10000
    let msg: ReturnType<Decoder["decode"]> | undefined;
    expect(() => {
      msg = dec.decode(synth(20, [{ num: 2, size: 8, baseType: 0x8f }], bytes));
    }).not.toThrow();
    // altitude: scale 5, offset 500 -> 10000/5 - 500 = 1500
    expect(msg?.fields.get("altitude")?.value).toBeCloseTo(1500, 10);
  });

  it("nulls the uint64 sentinel", () => {
    const dec = new Decoder();
    const msg = dec.decode(
      synth(
        0xffff,
        [{ num: 0, size: 8, baseType: 0x8f }],
        [255, 255, 255, 255, 255, 255, 255, 255],
      ),
    );
    expect(msg.fields.get("field_0")?.value).toBeNull();
  });
});

describe("salvage provenance ordering (amendment C1)", () => {
  // Also uncovered by the corpus: a mutation replacing the tuple sort with a
  // lexicographic one passed all 72 cases, because there are only six provenance
  // entries in total and no two ever disagree between the orderings.
  it("sorts by (definition offset, field number), not by string key", () => {
    const dec = new Decoder();
    // Definition offsets 100 and 20 with an unknown base type each. Lexicographically
    // "100 ..." sorts before "20 ..."; numerically 20 comes first.
    dec.decode(synth(0xffff, [{ num: 1, size: 2, baseType: 0x7e }], [0, 0], { offset: 100 }));
    dec.decode(synth(0xffff, [{ num: 1, size: 2, baseType: 0x7e }], [0, 0], { offset: 20 }));
    const out = dec.finish();
    const scopes = out.provenance
      .filter((p) => p.code === "FIELD_RAW_SALVAGED")
      .map((p) => p.scope);
    expect(scopes).toEqual(["definition@20.field_1", "definition@100.field_1"]);
  });

  it("aggregates repeats and keeps the first offset", () => {
    const dec = new Decoder();
    for (let i = 0; i < 3; i++) {
      dec.decode(synth(0xffff, [{ num: 1, size: 2, baseType: 0x7e }], [0, 0], { offset: 40 }));
    }
    const out = dec.finish();
    const entry = out.provenance.find((p) => p.code === "FIELD_RAW_SALVAGED");
    expect(entry?.detail).toContain("3 message(s)");
    expect(entry?.data.count).toBe(3);
  });

  it("raises the defect only once for a repeated salvage", () => {
    const dec = new Decoder();
    for (let i = 0; i < 3; i++) {
      dec.decode(synth(0xffff, [{ num: 1, size: 2, baseType: 0x7e }], [0, 0], { offset: 40 }));
    }
    const out = dec.finish();
    expect(out.defects.filter((d) => d.code === "FIT_BASE_TYPE_INVALID")).toHaveLength(1);
  });
});

describe("diagnostics", () => {
  it("emits each (code, scope) at most once, in production order", () => {
    const dec = new Decoder();
    for (let i = 0; i < 3; i++) {
      // local_date_time below the ceiling: device-relative, diagnosed once.
      dec.decode(synth(0xffff, [{ num: 0, size: 4, baseType: 0x86 }], [1, 0, 0, 0]));
    }
    const out = dec.finish();
    const codes = out.diagnostics.map((d) => d.code);
    expect(new Set(codes).size).toBe(codes.length);
  });
});

describe("unknown tolerance — contract #6", () => {
  it("names an unknown message and its fields rather than failing", () => {
    const dec = new Decoder();
    const msg = dec.decode(synth(64999, [{ num: 7, size: 2, baseType: 0x84 }], [1, 0]));
    expect(msg.name).toBe("unknown_64999");
    expect(msg.fields.get("field_7")?.value).toBe(1);
  });

  it("returns the raw int for an unknown enum value", () => {
    const dec = new Decoder();
    const msg = dec.decode(synth(18, [{ num: 5, size: 1, baseType: 0x00 }], [250]));
    expect(msg.fields.get("sport")?.value).toBe(250);
  });

  it("salvages an unknown base type without throwing", () => {
    const dec = new Decoder();
    const msg = dec.decode(synth(0xffff, [{ num: 1, size: 2, baseType: 0x7e }], [1, 2]));
    expect(msg.fields.get("field_1")?.value).toBeNull();
    expect(dec.finish().defects.some((d) => d.code === "FIT_BASE_TYPE_INVALID")).toBe(true);
  });
});

describe("iterMessages", () => {
  it("decodes a clean file", () => {
    const messages = [...iterMessages(rideSmooth)];
    expect(messages.length).toBeGreaterThan(0);
    expect(messages[0]?.name).toBe("file_id");
    expect(messages.some((m) => m.name === "record")).toBe(true);
  });

  it("never throws on a truncation sweep", () => {
    for (let cut = 0; cut <= rideSmooth.length; cut += 3) {
      expect(() => {
        for (const _ of iterMessages(rideSmooth.subarray(0, cut))) {
          // drain
        }
      }, `throw at cut ${cut}`).not.toThrow();
    }
  });

  it("endianness is honored", () => {
    const dec = new Decoder();
    const le = dec.decode(synth(20, [{ num: 7, size: 2, baseType: 0x84 }], [0x01, 0x02]));
    const be = new Decoder().decode(
      synth(20, [{ num: 7, size: 2, baseType: 0x84 }], [0x01, 0x02], { bigEndian: true }),
    );
    expect(le.fields.get("power")?.value).toBe(0x0201);
    expect(be.fields.get("power")?.value).toBe(0x0102);
  });
});
