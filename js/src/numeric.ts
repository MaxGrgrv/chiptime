/**
 * The number kernel — Python arithmetic semantics, ported explicitly.
 *
 * INTERNAL. Not exported from `index.ts` and not part of the published API:
 * Python has no such module (the stdlib fills the role), so this is the one
 * deliberate break in the module-for-module mirror (ADR-0009 §3, F31 spec A5).
 *
 * Every function here exists because a JavaScript built-in disagrees with Python
 * on a value that reaches canonical output. `Math.round` is banned everywhere
 * else in `js/src` — see `scripts/guards.mjs`.
 */

/**
 * `round(x)` — round-half-to-even, Python's built-in single-argument form.
 *
 * `Math.round` is half-*up*: `Math.round(2.5)` is 3 where Python gives 2, and
 * `Math.round(-0.5)` is -0 where Python gives 0.
 *
 * Exact for |x| < 2**53. Beyond that a double is already integral and is returned
 * unchanged — where Python would return an exact int, JavaScript has no wider
 * integer to return, and no caller in this port reaches that magnitude.
 */
export function pyRound(x: number): number {
  if (!Number.isFinite(x)) return x;
  const floor = Math.floor(x);
  // Exact: for |x| < 2**52 the subtraction is representable; at or above it the
  // value is integral and `diff` is 0.
  const diff = x - floor;
  let result: number;
  if (diff > 0.5) result = floor + 1;
  else if (diff < 0.5) result = floor;
  else result = floor % 2 === 0 ? floor : floor + 1;
  // Python's round() returns an int, and an int has no negative zero: round(-0.0)
  // is 0, not -0. Math.floor(-0) is -0, so normalize before returning.
  return result === 0 ? 0 : result;
}

/**
 * `round(x, n)` — round the **exact binary value** of `x` half-to-even at `n`
 * decimal places, then return the nearest double. Python's two-argument form.
 *
 * Both tempting shortcuts are wrong, and the vectors pin both:
 *
 *   Math.round(x * 10 ** n) / 10 ** n
 *       the multiplication adds its own error. round(2.675, 2) is 2.67; this gives 2.68.
 *
 *   x.toFixed(n)
 *       ECMA-262 rounds exact ties *away from zero*; Python rounds them half-to-even.
 *       (0.125).toFixed(2) is "0.13"; round(0.125, 2) is 0.12.
 *
 * So the value is decomposed into its exact `mantissa × 2**exponent` form and the
 * rounding is done in integer arithmetic, where ties are unambiguous.
 */
export function pyRoundN(x: number, n: number): number {
  if (!Number.isInteger(n) || n < 0) {
    throw new RangeError(`pyRoundN: n must be a non-negative integer, got ${n}`);
  }
  if (!Number.isFinite(x) || x === 0) return x; // preserves -0, as Python preserves -0.0
  const negative = x < 0;
  const { mantissa, exp2 } = decompose(Math.abs(x));
  const pow10 = 10n ** BigInt(n);

  let scaled: bigint;
  if (exp2 >= 0) {
    // |x| * 10**n is exactly an integer; there is nothing to round.
    scaled = mantissa * (1n << BigInt(exp2)) * pow10;
  } else {
    const numerator = mantissa * pow10;
    const denominator = 1n << BigInt(-exp2);
    scaled = divRoundHalfEven(numerator, denominator);
  }

  const value = Number(decimalString(scaled, n));
  return negative ? -value : value;
}

/** `a // b` — Python floor division. JavaScript's `/` truncates toward zero. */
export function floorDiv(a: number, b: number): number {
  return Math.floor(a / b);
}

/**
 * `divmod(a, b)` — Python's pair, where the remainder takes the sign of the
 * divisor: `divmod(-7, 3)` is `[-3, 2]`, while JavaScript's `%` gives `-1`.
 */
export function divmod(a: number, b: number): [number, number] {
  const q = Math.floor(a / b);
  return [q, a - b * q];
}

/** Exact `|x| = mantissa * 2**exp2` for a finite non-zero double. */
function decompose(x: number): { mantissa: bigint; exp2: number } {
  const view = new DataView(new ArrayBuffer(8));
  view.setFloat64(0, x);
  const hi = view.getUint32(0);
  const lo = view.getUint32(4);
  const biasedExponent = (hi >>> 20) & 0x7ff;
  const fraction = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo);
  if (biasedExponent === 0) {
    return { mantissa: fraction, exp2: -1074 }; // subnormal: no implicit leading bit
  }
  return { mantissa: fraction | (1n << 52n), exp2: biasedExponent - 1075 };
}

/** `numerator / denominator` rounded half-to-even, both positive. */
function divRoundHalfEven(numerator: bigint, denominator: bigint): bigint {
  const quotient = numerator / denominator;
  const remainder = numerator - quotient * denominator;
  const twice = remainder * 2n;
  if (twice > denominator) return quotient + 1n;
  if (twice < denominator) return quotient;
  return quotient % 2n === 0n ? quotient : quotient + 1n; // exact tie
}

/** Render `scaled / 10**n` as a decimal string; `Number()` of it is correctly rounded. */
function decimalString(scaled: bigint, n: number): string {
  if (n === 0) return scaled.toString();
  const digits = scaled.toString().padStart(n + 1, "0");
  return `${digits.slice(0, -n)}.${digits.slice(-n)}`;
}

/**
 * `str(x)` for a Python **float**.
 *
 * Python prints an integral float with its fractional part — `str(55.0)` is
 * `"55.0"` — while JavaScript's `String(55)` gives `"55"`, because it has no
 * float/int distinction. The difference is invisible in canonical JSON (ES6 number
 * formatting drops the `.0` on both sides) but very visible in the provenance and
 * diagnostic *strings* that interpolate these values.
 *
 * Only for values Python holds as floats. Integers must not go through this.
 */
export function pyFloatStr(x: number): string {
  if (!Number.isFinite(x)) return x > 0 ? "inf" : Number.isNaN(x) ? "nan" : "-inf";
  return Number.isInteger(x) ? `${x}.0` : String(x);
}
