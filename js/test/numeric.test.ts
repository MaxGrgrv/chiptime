import { describe, expect, it } from "vitest";
import { divmod, floorDiv, pyRound, pyRoundN } from "../src/numeric.js";
import { numericVectors } from "./vectors.js";

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
