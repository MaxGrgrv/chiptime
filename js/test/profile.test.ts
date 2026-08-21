import { describe, expect, it } from "vitest";
import { BASE_TYPES, BASE_TYPES_BY_NAME, isInvalid } from "../src/profile/base-types.js";
import { ENUMS, MESSAGES, SEMICIRCLE_SCALE } from "../src/profile/index.js";
import { lookup } from "../src/profile/registry.js";
import { baseTypeVectors } from "./vectors.js";

const SIXTY_FOUR_BIT = new Set(["sint64", "uint64", "uint64z", "float64"]);

describe("isInvalid — differential against CPython", () => {
  for (const v of baseTypeVectors) {
    it(`${v.type}(${v.value}) -> ${v.expected}`, () => {
      const bt = BASE_TYPES_BY_NAME[v.type];
      expect(bt).toBeDefined();
      if (bt === undefined) return;
      let value: number | bigint;
      if (v.value === "nan") {
        value = Number.NaN;
      } else if (SIXTY_FOUR_BIT.has(v.type) && v.type !== "float64") {
        value = BigInt(v.value);
      } else {
        value = Number(v.value);
      }
      expect(isInvalid(bt, value)).toBe(v.expected);
    });
  }
});

describe("base types", () => {
  it("carries all seventeen rows, addressable by byte and by name", () => {
    expect(Object.keys(BASE_TYPES)).toHaveLength(17);
    expect(Object.keys(BASE_TYPES_BY_NAME)).toHaveLength(17);
    expect(BASE_TYPES[0x84]?.name).toBe("uint16");
    expect(BASE_TYPES_BY_NAME.uint16?.byte).toBe(0x84);
  });

  it("keeps 64-bit sentinels as exact bigints", () => {
    // The reason this matters: as a number, 0xFFFFFFFFFFFFFFFF rounds to
    // 18446744073709552000 and stops being the sentinel it is meant to detect.
    expect(BASE_TYPES_BY_NAME.uint64?.invalid).toBe(0xffffffffffffffffn);
    expect(BASE_TYPES_BY_NAME.sint64?.invalid).toBe(0x7fffffffffffffffn);
    expect(BASE_TYPES_BY_NAME.uint64z?.invalid).toBe(0n);
    // Round-tripping the sentinel through a double loses it: the nearest double is
    // 18446744073709552000, so a number-typed sentinel would stop matching the value
    // it exists to detect.
    expect(BigInt(Number(0xffffffffffffffffn))).not.toBe(0xffffffffffffffffn);
  });

  it("answers rather than throws when a corrupt read puts NaN against a 64-bit type", () => {
    // Nothing in the decode path may crash on hostile input, and BigInt(NaN) throws.
    for (const name of ["uint64", "sint64", "uint64z"]) {
      const bt = BASE_TYPES_BY_NAME[name];
      expect(bt).toBeDefined();
      if (bt === undefined) continue;
      expect(() => isInvalid(bt, Number.NaN)).not.toThrow();
      expect(isInvalid(bt, Number.NaN)).toBe(false);
      expect(isInvalid(bt, Number.POSITIVE_INFINITY)).toBe(false);
      expect(isInvalid(bt, 1.5)).toBe(false);
    }
  });

  it("names a DataView accessor for every numeric type and none for string/byte", () => {
    for (const bt of Object.values(BASE_TYPES)) {
      if (bt.name === "string" || bt.name === "byte") {
        expect(bt.accessor).toBeNull();
      } else {
        expect(bt.accessor).not.toBeNull();
        expect(new DataView(new ArrayBuffer(8))[bt.accessor as "getUint8"]).toBeTypeOf("function");
      }
    }
  });

  it("treats a float sentinel as invalid only when it arrives as NaN", () => {
    const f32 = BASE_TYPES_BY_NAME.float32;
    expect(f32).toBeDefined();
    if (f32 === undefined) return;
    // The all-ones bit pattern reads back as NaN; the integer itself is a real value.
    expect(isInvalid(f32, Number.NaN)).toBe(true);
    expect(isInvalid(f32, 0xffffffff)).toBe(false);
  });
});

describe("merged tables", () => {
  it("carries the full profile", () => {
    expect(Object.keys(MESSAGES)).toHaveLength(119);
    expect(Object.keys(ENUMS)).toHaveLength(176);
  });

  it("resolves the messages decode leans on", () => {
    expect(MESSAGES[20]?.name).toBe("record");
    expect(MESSAGES[0]?.name).toBe("file_id");
    expect(MESSAGES[18]?.name).toBe("session");
    expect(MESSAGES[20]?.fields[253]?.name).toBe("timestamp");
  });

  it("keeps the hand-authored core's scale and units (the merge landed)", () => {
    const record = MESSAGES[20];
    expect(record).toBeDefined();
    // altitude is /5 - 500 (taxonomy #27); a merge that dropped the verified core
    // would leave the generated defaults here instead.
    expect(record?.fields[2]?.name).toBe("altitude");
    expect(record?.fields[2]?.scale).toBe(5);
    expect(record?.fields[2]?.offset).toBe(500);
  });

  it("carries the semicircle scale as the same value Python computes", () => {
    expect(SEMICIRCLE_SCALE).toBe(2 ** 31 / 180);
    expect(MESSAGES[20]?.fields[0]?.name).toBe("position_lat");
    expect(MESSAGES[20]?.fields[0]?.scale).toBe(SEMICIRCLE_SCALE);
  });

  it("preserves non-integral scales exactly", () => {
    // A scale off by one ULP silently mis-scales every value in its field, and no
    // provenance entry would record it. These are the awkward ones in the profile.
    const scales = new Set<number>();
    for (const m of Object.values(MESSAGES)) {
      for (const f of Object.values(m.fields)) {
        if (f.scale !== Math.trunc(f.scale)) scales.add(f.scale);
      }
    }
    expect(scales).toContain(0.7111111);
    expect(scales).toContain(28.57143);
    expect(scales).toContain(10430.38);
    expect(scales).toContain(1.024);
  });

  it("resolves enum labels", () => {
    expect(ENUMS.sport?.[2]).toBe("cycling");
    expect(ENUMS.file?.[4]).toBe("activity");
  });
});

describe("unknown tolerance — contract #6", () => {
  // The one behavior this layer owns outright: a table that lacks an entry yields
  // nothing, never an error. A stale profile degrades; it never crashes a decode.
  it("returns undefined for an unknown message, field, and enum value", () => {
    expect(MESSAGES[64999]).toBeUndefined();
    expect(MESSAGES[20]?.fields[250]).toBeUndefined();
    expect(ENUMS.sport?.[64999]).toBeUndefined();
    expect(ENUMS.no_such_enum_type).toBeUndefined();
  });

  it("does not throw when asked about anything absent", () => {
    expect(() => MESSAGES[64999]?.fields[1]?.name).not.toThrow();
    expect(() => ENUMS.nope?.[1]).not.toThrow();
  });
});

describe("vendor developer-field registry", () => {
  it("promotes a known vendor field", () => {
    expect(lookup("stryd", "Power")).toEqual({ canonicalName: "running_power", units: "W" });
    expect(lookup("moxy", "SmO2")).toEqual({ canonicalName: "smo2", units: "percent" });
  });

  it("normalizes case and surrounding whitespace, as Python does", () => {
    expect(lookup("stryd", "  Leg Spring Stiffness  ")?.canonicalName).toBe("leg_spring_stiffness");
  });

  it("returns null for unknown vendors, unknown fields, and missing input", () => {
    expect(lookup("stryd", "not a field")).toBeNull();
    expect(lookup("acme", "power")).toBeNull();
    expect(lookup(null, "power")).toBeNull();
    expect(lookup("stryd", null)).toBeNull();
  });

  it("is not fooled by a prototype-chain key", () => {
    expect(lookup("constructor", "prototype")).toBeNull();
    expect(lookup("stryd", "__proto__")).toBeNull();
  });
});
