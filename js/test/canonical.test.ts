import { describe, expect, it } from "vitest";
import { CanonicalizationError, dumps, dumpsText, formatNumber } from "../src/canonical.js";
import { canonicalAsymmetry, canonicalOk, canonicalRefuse } from "./vectors.js";

const decoder = new TextDecoder("utf-8", { fatal: true });

describe("differential vectors (CPython is the reference)", () => {
  it("has vectors to run", () => {
    expect(canonicalOk.length).toBeGreaterThan(40);
  });

  for (const v of canonicalOk) {
    it(`matches CPython: ${v.name}`, () => {
      // Each side parses the same JSON *text* with its own reader, then serializes
      // with its own canonicalizer. That is the thing that actually has to match.
      const bytes = dumps(JSON.parse(v.input));
      expect(decoder.decode(bytes)).toBe(v.expected);
    });
  }

  for (const v of canonicalRefuse) {
    it(`refuses, as CPython does: ${v.name}`, () => {
      expect(() => dumps(JSON.parse(v.input))).toThrow(CanonicalizationError);
    });
  }

  for (const v of canonicalAsymmetry) {
    it(`documented asymmetry — CPython accepts, we refuse: ${v.name}`, () => {
      // Python's oversized-integer guard is type-based and cannot be reproduced in a
      // language with one number type. Refusing is the safe direction: it turns an
      // unrepresentable value into a loud failure instead of a silent one.
      expect(() => dumps(JSON.parse(v.input))).toThrow(/exceeds 2\*\*53-1/);
      expect(v.pythonOutput).not.toBe("");
    });
  }
});

describe("Map and plain objects are interchangeable", () => {
  it("serializes a Map exactly like the equivalent object", () => {
    const asObject = { b: 1, a: [1, 2], c: null };
    const asMap = new Map<string, unknown>([
      ["b", 1],
      ["a", [1, 2]],
      ["c", null],
    ]);
    expect(dumpsText(asMap)).toBe(dumpsText(asObject));
    expect(dumpsText(asMap)).toBe('{"a":[1,2],"b":1,"c":null}');
  });

  it("sorts Map keys rather than trusting insertion order", () => {
    expect(
      dumpsText(
        new Map([
          ["z", 1],
          ["a", 2],
        ]),
      ),
    ).toBe('{"a":2,"z":1}');
  });

  it("refuses a non-string Map key", () => {
    expect(() => dumps(new Map([[1, "a"]]))).toThrow(/non-string key/);
  });

  it("serializes nested Maps", () => {
    expect(dumpsText(new Map<string, unknown>([["a", new Map([["b", 1]])]]))).toBe('{"a":{"b":1}}');
  });
});

describe("refuses what JSON.stringify would silently mangle", () => {
  // Each of these would put wrong data into canonical output with no provenance
  // entry, and the serializer has no provenance to emit (contract #1).
  it("refuses binary data instead of emitting an index map", () => {
    expect(JSON.stringify(new Uint8Array([31, 139]))).toBe('{"0":31,"1":139}'); // the hazard
    expect(() => dumps(new Uint8Array([31, 139]))).toThrow(/hex-encode/);
    expect(() => dumps({ crc: new Uint8Array([1]) })).toThrow(/hex-encode/);
    expect(() => dumps(new ArrayBuffer(4))).toThrow(/hex-encode/);
  });

  it("refuses Date instead of emitting a millisecond-bearing ISO string", () => {
    const d = new Date(Date.UTC(2026, 6, 30, 17, 2, 11));
    expect(d.toISOString()).toBe("2026-07-30T17:02:11.000Z"); // the hazard: .000
    expect(() => dumps(d)).toThrow(/Date reached serialization/);
  });

  it("refuses an array hole instead of turning it into null", () => {
    const sparse = [1, 2, 3];
    // biome-ignore lint/performance/noDelete: constructing the hazard is the point
    delete sparse[1];
    expect(JSON.stringify(sparse)).toBe("[1,null,3]"); // the hazard: zero-vs-null
    expect(() => dumps(sparse)).toThrow(/sparse array/);
    expect(() => dumps(new Array(3))).toThrow(/sparse array/);
  });

  it("refuses an object that redirects its own serialization", () => {
    expect(() => dumps({ toJSON: () => 1 })).toThrow(/toJSON/);
  });

  it("refuses class instances, as Python refuses non-dict objects", () => {
    class Totals {
      distanceM = 1;
    }
    expect(() => dumps(new Totals())).toThrow(/unserializable type/);
    expect(() => dumps(new Set([1]))).toThrow(/unserializable type/);
  });

  it("accepts a null-prototype object", () => {
    const bare = Object.create(null) as Record<string, unknown>;
    bare.a = 1;
    expect(dumpsText(bare)).toBe('{"a":1}');
  });
});

describe("number policy (ADR-0002 §2)", () => {
  it("refuses NaN and infinities", () => {
    expect(() => formatNumber(Number.NaN)).toThrow(/NaN\/Infinity/);
    expect(() => formatNumber(Number.POSITIVE_INFINITY)).toThrow(/NaN\/Infinity/);
    expect(() => formatNumber(Number.NEGATIVE_INFINITY)).toThrow(/NaN\/Infinity/);
    expect(() => dumps({ v: Number.NaN })).toThrow(CanonicalizationError);
  });

  it("serializes -0 as 0", () => {
    expect(formatNumber(-0)).toBe("0");
    expect(dumpsText([-0, 0])).toBe("[0,0]");
  });

  it("refuses bigint, deferring to the shaping layer's decimal-string policy", () => {
    expect(() => dumps(123n)).toThrow(/decimal string/);
    expect(() => dumps({ serial: 18446744073709551615n })).toThrow(/decimal string/);
  });

  it("accepts the safe-integer boundary and refuses one past it", () => {
    expect(formatNumber(9007199254740991)).toBe("9007199254740991");
    expect(formatNumber(-9007199254740991)).toBe("-9007199254740991");
    expect(() => formatNumber(9007199254740992)).toThrow(/exceeds/);
  });
});

describe("refuses non-JSON values", () => {
  it("refuses undefined rather than inventing an absence", () => {
    expect(() => dumps(undefined)).toThrow(/undefined is not a JSON value/);
    expect(() => dumps({ a: undefined })).toThrow(/undefined is not a JSON value/);
    expect(() => dumps([undefined])).toThrow(/undefined is not a JSON value/);
  });

  it("refuses functions and symbols", () => {
    expect(() => dumps(() => 1)).toThrow(/unserializable type function/);
    expect(() => dumps(Symbol("x"))).toThrow(/unserializable type symbol/);
  });
});

describe("UTF-8 encoding", () => {
  it("encodes astral characters as four bytes", () => {
    expect([...dumps("\u{1F680}")]).toEqual([0x22, 0xf0, 0x9f, 0x9a, 0x80, 0x22]);
  });

  it("refuses unpaired surrogates, as CPython's .encode('utf-8') does", () => {
    // TextEncoder would substitute U+FFFD here — a silent character swap.
    expect(() => dumps("\ud800")).toThrow(/unpaired high surrogate/);
    expect(() => dumps("\udc00")).toThrow(/unpaired low surrogate/);
    expect(() => dumps("a\ud800b")).toThrow(/unpaired high surrogate/);
    expect(() => dumps({ "\ud800": 1 })).toThrow(/unpaired high surrogate/);
  });

  it("returns bytes, not a string", () => {
    expect(dumps({ a: 1 })).toBeInstanceOf(Uint8Array);
  });
});

describe("determinism", () => {
  it("is byte-identical across repeated calls and key insertion orders", () => {
    const a = { z: 1, a: { c: 3, b: 2 }, m: [1, 2, 3] };
    const b = { m: [1, 2, 3], a: { b: 2, c: 3 }, z: 1 };
    expect(dumpsText(a)).toBe(dumpsText(b));
    expect(dumps(a)).toEqual(dumps(a));
  });
});
