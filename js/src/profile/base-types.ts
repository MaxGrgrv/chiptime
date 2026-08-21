/**
 * FIT base types: wire sizes, `DataView` accessors, and per-type invalid sentinels.
 *
 * Twin of `python/src/chiptime/profile/base_types.py`. Hand-written and reviewed
 * rather than generated: seventeen rows of protocol constants that change when the
 * FIT spec does -- approximately never -- and a generator would be more code than
 * the table.
 *
 * The definition frame's base-type byte is authoritative for decoding width; bit 7
 * marks multi-byte (endian-sensitive) types, bits 0-4 the type number.
 */

/**
 * How to read this type out of a `DataView`.
 *
 * Python's table carries a `struct` format character, which names nothing this
 * runtime has. This is the same fact in the form TypeScript can use. `null` for
 * string and byte, which the decoder handles specially.
 */
export type Accessor =
  | "getInt8"
  | "getUint8"
  | "getInt16"
  | "getUint16"
  | "getInt32"
  | "getUint32"
  | "getFloat32"
  | "getFloat64"
  | "getBigInt64"
  | "getBigUint64";

export interface BaseType {
  readonly byte: number;
  readonly name: string;
  readonly size: number;
  /** `null` for string/byte, which the decoder handles specially. */
  readonly accessor: Accessor | null;
  /**
   * Sentinel meaning "absent" (taxonomy #26); `null` where the type has none.
   *
   * `bigint` for the 64-bit rows: `uint64`'s sentinel is 0xFFFFFFFFFFFFFFFF and
   * `float64`'s bit pattern is the same value, both far beyond
   * `Number.MAX_SAFE_INTEGER` (ADR-0009 section 4).
   */
  readonly invalid: number | bigint | null;
}

const TYPES: readonly BaseType[] = [
  { byte: 0x00, name: "enum", size: 1, accessor: "getUint8", invalid: 0xff },
  { byte: 0x01, name: "sint8", size: 1, accessor: "getInt8", invalid: 0x7f },
  { byte: 0x02, name: "uint8", size: 1, accessor: "getUint8", invalid: 0xff },
  { byte: 0x83, name: "sint16", size: 2, accessor: "getInt16", invalid: 0x7fff },
  { byte: 0x84, name: "uint16", size: 2, accessor: "getUint16", invalid: 0xffff },
  { byte: 0x85, name: "sint32", size: 4, accessor: "getInt32", invalid: 0x7fffffff },
  { byte: 0x86, name: "uint32", size: 4, accessor: "getUint32", invalid: 0xffffffff },
  { byte: 0x07, name: "string", size: 1, accessor: null, invalid: null },
  { byte: 0x88, name: "float32", size: 4, accessor: "getFloat32", invalid: 0xffffffff },
  { byte: 0x89, name: "float64", size: 8, accessor: "getFloat64", invalid: 0xffffffffffffffffn },
  { byte: 0x0a, name: "uint8z", size: 1, accessor: "getUint8", invalid: 0x00 },
  { byte: 0x8b, name: "uint16z", size: 2, accessor: "getUint16", invalid: 0x0000 },
  { byte: 0x8c, name: "uint32z", size: 4, accessor: "getUint32", invalid: 0x00000000 },
  { byte: 0x0d, name: "byte", size: 1, accessor: null, invalid: null },
  { byte: 0x8e, name: "sint64", size: 8, accessor: "getBigInt64", invalid: 0x7fffffffffffffffn },
  { byte: 0x8f, name: "uint64", size: 8, accessor: "getBigUint64", invalid: 0xffffffffffffffffn },
  { byte: 0x90, name: "uint64z", size: 8, accessor: "getBigUint64", invalid: 0x0000000000000000n },
];

export const BASE_TYPES: Readonly<Record<number, BaseType>> = Object.freeze(
  Object.fromEntries(TYPES.map((t) => [t.byte, t])),
);

export const BASE_TYPES_BY_NAME: Readonly<Record<string, BaseType>> = Object.freeze(
  Object.fromEntries(TYPES.map((t) => [t.name, t])),
);

/**
 * Signed sentinels arrive as negative values after an unsigned read; precompute,
 * exactly as `base_types.py` does.
 */
const SIGNED_INVALID: Readonly<Record<string, number | bigint>> = Object.freeze({
  sint8: 0x7f,
  sint16: 0x7fff,
  sint32: 0x7fffffff,
  sint64: 0x7fffffffffffffffn,
});

/** True when the wire value is the base type's "invalid" sentinel. */
export function isInvalid(bt: BaseType, value: number | bigint): boolean {
  if (bt.invalid === null) return false;
  if (bt.name === "float32" || bt.name === "float64") {
    // The sentinel is the all-ones bit pattern, which reads back as NaN. Any NaN is
    // unusable anyway; the caller distinguishes NaN-from-sentinel for diagnostics by
    // inspecting bits if it needs to.
    return typeof value === "number" && Number.isNaN(value);
  }
  const sentinel = SIGNED_INVALID[bt.name] ?? bt.invalid;
  if (typeof value === typeof sentinel) return value === sentinel;

  // Mixed number/bigint: a 64-bit read and a number sentinel (or the reverse) can
  // describe the same wire value, so compare on common ground. Python's `==` does
  // this silently; `BigInt()` throws on NaN, Infinity, and non-integers, so the
  // conversion is guarded. Answering `false` is not a fallback — a non-integral or
  // non-finite value simply cannot equal an integer sentinel, which is exactly what
  // Python concludes.
  //
  // This must never throw: a corrupt float read can put NaN here, and nothing in the
  // decode path is allowed to crash on hostile input.
  if (typeof value === "number") {
    return Number.isInteger(value) && BigInt(value) === (sentinel as bigint);
  }
  return Number.isInteger(sentinel) && value === BigInt(sentinel as number);
}
