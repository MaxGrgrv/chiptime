import { describe, expect, it } from "vitest";
import {
  divmod,
  floorDiv,
  pyFixed,
  pyFloatStr,
  pyG,
  pyRound,
  pyRoundN,
  pySum,
} from "../src/numeric.js";
import { formatVectors, numericVectors } from "./vectors.js";

describe("pyRound — round-half-to-even", () => {
  for (const [x, expected] of numericVectors.pyRound) {
    it(`round(${x}) === ${expected}`, () => {
      expect(Object.is(pyRound(x), expected)).toBe(true);
    });
  }

  it("differs from Math.round exactly where Python does", () => {
    expect(Math.round(2.5)).toBe(3);
    expect(pyRound(2.5)).toBe(2);
    expect(Object.is(Math.round(-0.5), -0)).toBe(true);
    expect(Object.is(pyRound(-0.5), 0)).toBe(true);
  });

  it("does not round 0.49999999999999994 up", () => {
    expect(pyRound(0.49999999999999994)).toBe(0);
  });
});

describe("pyRoundN — half-to-even on the exact binary value", () => {
  for (const [x, n, expected] of numericVectors.pyRoundN) {
    it(`round(${x}, ${n}) === ${expected}`, () => {
      expect(Object.is(pyRoundN(x, n), expected)).toBe(true);
    });
  }

  it("defeats the toFixed shortcut on exact ties", () => {
    expect((0.125).toFixed(2)).toBe("0.13"); // ECMA-262: ties away from zero
    expect(pyRoundN(0.125, 2)).toBe(0.12); // Python: ties to even
  });

  it("defeats the multiply-round-divide shortcut", () => {
    expect(Math.round(2.675 * 100) / 100).toBe(2.68);
    expect(pyRoundN(2.675, 2)).toBe(2.67);
  });

  it("preserves negative zero", () => {
    expect(Object.is(pyRoundN(-0, 2), -0)).toBe(true);
  });

  it("passes non-finite values through, as Python does", () => {
    expect(pyRoundN(Number.POSITIVE_INFINITY, 2)).toBe(Number.POSITIVE_INFINITY);
    expect(Number.isNaN(pyRoundN(Number.NaN, 2))).toBe(true);
  });

  it("rejects a negative or fractional precision", () => {
    expect(() => pyRoundN(1.5, -1)).toThrow(RangeError);
    expect(() => pyRoundN(1.5, 1.5)).toThrow(RangeError);
  });

  it("handles subnormals without losing the value", () => {
    expect(pyRoundN(5e-324, 4)).toBe(0);
  });
});

describe("floorDiv and divmod — Python floor semantics", () => {
  for (const [a, b, expected] of numericVectors.floorDiv) {
    it(`${a} // ${b} === ${expected}`, () => {
      expect(floorDiv(a, b)).toBe(expected);
    });
  }

  for (const [a, b, expected] of numericVectors.divmod) {
    it(`divmod(${a}, ${b}) === [${expected.join(", ")}]`, () => {
      expect(divmod(a, b)).toEqual(expected);
    });
  }

  it("gives the remainder the sign of the divisor, unlike %", () => {
    expect(-7 % 3).toBe(-1);
    expect(divmod(-7, 3)[1]).toBe(2);
  });
});

describe("pySum — CPython's sum() is compensated, not naive", () => {
  for (const [i, v] of formatVectors.pySum.entries()) {
    it(`vector ${i} (${v.values.length} values) === ${v.sum}`, () => {
      expect(Object.is(pySum(v.values), v.sum)).toBe(true);
    });
  }

  it("differs from a naive accumulation where it matters", () => {
    // The find that cost 18 corpus cases at F36: CPython >= 3.12 runs the improved
    // Kahan-Babuska (Neumaier) algorithm in sum()'s float fast path. `total += v`
    // is what sum() *looks* like and is not what it does.
    const vals = new Array(120).fill(8.333);
    let naive = 0;
    for (const v of vals) naive += v;
    expect(naive).toBe(999.959999999999);
    expect(pySum(vals)).toBe(999.96);
  });
});

describe("pyFixed and pyFloatStr — formatting, differential against CPython", () => {
  for (const v of formatVectors.pyFixed) {
    it(`f"{${v.x}:.${v.n}f}" === ${JSON.stringify(v.text)}`, () => {
      expect(pyFixed(v.x, v.n)).toBe(v.text);
    });
  }

  for (const v of formatVectors.pyFloatStr) {
    it(`str(${v.x}) === ${JSON.stringify(v.text)}`, () => {
      expect(pyFloatStr(v.x)).toBe(v.text);
    });
  }

  it("differs from toFixed on exact ties, and from String() on integral floats", () => {
    expect((0.125).toFixed(2)).toBe("0.13");
    expect(pyFixed(0.125, 2)).toBe("0.12");
    expect(String(55)).toBe("55");
    expect(pyFloatStr(55.0)).toBe("55.0");
  });
});

describe("pyG — Python's general format, differential against CPython", () => {
  for (const v of formatVectors.pyG) {
    it(`f"{${v.x}:g}" === ${JSON.stringify(v.text)}`, () => {
      expect(pyG(v.x)).toBe(v.text);
    });
  }

  it("is not String()", () => {
    expect(String(1234.5678)).toBe("1234.5678");
    expect(pyG(1234.5678)).toBe("1234.57");
    expect(String(1e-5)).toBe("0.00001");
    expect(pyG(1e-5)).toBe("1e-05");
  });
});
