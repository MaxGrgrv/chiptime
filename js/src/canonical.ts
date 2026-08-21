/**
 * RFC 8785 (JCS) canonical JSON serialization — the determinism contract.
 *
 * Twin of `python/src/chiptime/canonical.py`. See ADR-0002 for the scheme and the
 * 64-bit policy, ADR-0009 §2/§4 for what parity means between the two.
 *
 * Accepts only the JSON value tree: null | boolean | string | number | Array |
 * Map<string, unknown> | plain object. Everything else is refused, because the
 * alternative is not "a different shape" but silent corruption — see
 * `CanonicalizationError` below.
 */

/** Largest integer JSON can carry without precision loss (ADR-0002 §2). */
export const MAX_SAFE_INT = Number.MAX_SAFE_INTEGER; // 2**53 - 1

/**
 * A value that must never reach serialization did (bug guard, ADR-0002).
 *
 * This is an internal invariant failure, not an agent-facing error: it carries no
 * machine code and no suggestion, exactly like the `ValueError` subclass it mirrors
 * in Python. If a user ever sees one, the bug is upstream in the shaping layer.
 */
export class CanonicalizationError extends Error {
  override readonly name = "CanonicalizationError";
}

/** Serialize to canonical JSON bytes (UTF-8, JCS rules). */
export function dumps(value: unknown): Uint8Array {
  const parts: string[] = [];
  write(value, parts);
  return encodeUtf8(parts.join(""));
}

/** Serialize to the canonical JSON *string* (mainly for tests and diagnostics). */
export function dumpsText(value: unknown): string {
  const parts: string[] = [];
  write(value, parts);
  return parts.join("");
}

function write(value: unknown, out: string[]): void {
  if (value === null) {
    out.push("null");
    return;
  }
  switch (typeof value) {
    case "boolean":
      out.push(value ? "true" : "false");
      return;
    case "string":
      out.push(encodeString(value));
      return;
    case "number":
      out.push(formatNumber(value));
      return;
    case "bigint":
      // ADR-0002 §2: 64-bit raw values are the shaping layer's job to stringify.
      throw new CanonicalizationError(
        `bigint ${value} reached serialization; the shaping layer must emit it as a decimal string`,
      );
    case "undefined":
      // Python has no `undefined`. Serializing it as null would invent an absence
      // that the shaping layer never declared (contract #1).
      throw new CanonicalizationError("undefined is not a JSON value (did you mean null?)");
    case "function":
    case "symbol":
      throw new CanonicalizationError(`unserializable type ${typeof value}`);
    default:
      break;
  }
  if (Array.isArray(value)) {
    writeArray(value, out);
    return;
  }
  if (value instanceof Map) {
    writeObject(entriesOfMap(value), out);
    return;
  }
  refuseMangled(value);
  writeObject(Object.entries(value as Record<string, unknown>), out);
}

function writeArray(arr: unknown[], out: string[]): void {
  out.push("[");
  for (let i = 0; i < arr.length; i++) {
    // A hole is not an absence. JSON.stringify renders one as `null`, which is
    // precisely the zero-vs-null confusion contract #4 exists to prevent.
    if (!(i in arr)) {
      throw new CanonicalizationError(`sparse array: index ${i} is a hole, not a value`);
    }
    if (i > 0) out.push(",");
    write(arr[i], out);
  }
  out.push("]");
}

function writeObject(entries: [string, unknown][], out: string[]): void {
  // JCS: sort by UTF-16 code units. JavaScript's `<` on strings compares code
  // units, which is the same order `canonical.py` reaches via utf-16-be bytes.
  // Spelled out rather than left to the default comparator, because the default
  // comparator being correct here is a fact worth stating.
  const sorted = [...entries].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  out.push("{");
  for (let i = 0; i < sorted.length; i++) {
    const entry = sorted[i];
    if (entry === undefined) continue; // unreachable; satisfies noUncheckedIndexedAccess
    if (i > 0) out.push(",");
    out.push(encodeString(entry[0]), ":");
    write(entry[1], out);
  }
  out.push("}");
}

function entriesOfMap(map: Map<unknown, unknown>): [string, unknown][] {
  const entries: [string, unknown][] = [];
  for (const [k, v] of map) {
    if (typeof k !== "string") {
      throw new CanonicalizationError(`non-string key ${String(k)}`);
    }
    entries.push([k, v]);
  }
  return entries;
}

/**
 * Refuse the values `JSON.stringify` would silently *mangle* rather than reject.
 *
 * Each of these would land wrong data in canonical output with no provenance entry,
 * and the serializer has no provenance to emit — so refusal is the only correct
 * behavior (contract #1). See ADR-0009 §5 for the `Date` case specifically.
 */
function refuseMangled(value: object): void {
  const tag = Object.prototype.toString.call(value);
  if (ArrayBuffer.isView(value) || value instanceof ArrayBuffer) {
    throw new CanonicalizationError(
      "binary data reached serialization; the shaping layer must hex-encode bytes " +
        '(JSON.stringify would emit {"0":31,"1":139,…})',
    );
  }
  if (tag === "[object Date]") {
    throw new CanonicalizationError(
      "Date reached serialization; toISOString() always emits milliseconds and would " +
        "diverge from the Python timestamp format (ADR-0009 §5)",
    );
  }
  if (typeof (value as { toJSON?: unknown }).toJSON === "function") {
    throw new CanonicalizationError(
      "object defines toJSON(), which would redirect serialization away from the shape " +
        "the shaping layer built",
    );
  }
  const proto = Object.getPrototypeOf(value) as object | null;
  if (proto !== null && proto !== Object.prototype) {
    // Mirrors Python accepting `dict` and refusing arbitrary objects.
    throw new CanonicalizationError(`unserializable type ${tag}`);
  }
}

/**
 * Format a number per ECMAScript `Number::toString` (the JCS requirement).
 *
 * `String(x)` *is* that algorithm — the forty lines of digit surgery in
 * `canonical.py:number()` exist to reach this exact behavior from Python, so the
 * TypeScript side must not reimplement it. Equivalence is settled by vectors
 * (`test/vectors/canonical-ok.json`), not by argument.
 */
export function formatNumber(x: number): string {
  if (Number.isNaN(x) || x === Number.POSITIVE_INFINITY || x === Number.NEGATIVE_INFINITY) {
    throw new CanonicalizationError(
      "NaN/Infinity must be nulled (with a diagnostic) before serialization",
    );
  }
  if (Number.isInteger(x) && Math.abs(x) > MAX_SAFE_INT) {
    // Python's guard is type-based (`isinstance(obj, int)`), so it accepts a *float*
    // of this magnitude and refuses an *int*. JavaScript has one number type and
    // cannot tell them apart, so this guard is value-based and is therefore stricter
    // on integral floats ≥ 2**53. No corpus snapshot contains such a value; see the
    // F31 spec, Risk 1, and `test/canonical.test.ts` for the asymmetry test.
    throw new CanonicalizationError(
      `integer ${x} exceeds 2**53-1; shape layer must serialize it as a string`,
    );
  }
  if (x === 0) return "0"; // covers -0
  return String(x);
}

const ESCAPES: ReadonlyMap<string, string> = new Map([
  ["\\", "\\\\"],
  ['"', '\\"'],
  ["\b", "\\b"],
  ["\f", "\\f"],
  ["\n", "\\n"],
  ["\r", "\\r"],
  ["\t", "\\t"],
]);

function encodeString(s: string): string {
  const out: string[] = ['"'];
  for (const ch of s) {
    const esc = ESCAPES.get(ch);
    if (esc !== undefined) {
      out.push(esc);
    } else if (ch < "\x20") {
      out.push(`\\u${ch.charCodeAt(0).toString(16).padStart(4, "0")}`);
    } else {
      out.push(ch);
    }
  }
  out.push('"');
  return out.join("");
}

/**
 * UTF-8 encode, refusing unpaired surrogates.
 *
 * Hand-rolled rather than `TextEncoder` for two reasons: it keeps the package free
 * of any environment lib (no DOM, no node:), and `TextEncoder` silently replaces an
 * unpaired surrogate with U+FFFD — substituting a character where Python's
 * `.encode("utf-8")` raises. Both implementations must refuse; only the exception
 * type differs.
 */
function encodeUtf8(s: string): Uint8Array {
  let buf = new Uint8Array(s.length + 16);
  let n = 0;
  const ensure = (extra: number): void => {
    if (n + extra <= buf.length) return;
    let size = buf.length * 2;
    while (size < n + extra) size *= 2;
    const next = new Uint8Array(size);
    next.set(buf.subarray(0, n));
    buf = next;
  };

  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    if (c < 0x80) {
      ensure(1);
      buf[n++] = c;
    } else if (c < 0x800) {
      ensure(2);
      buf[n++] = 0xc0 | (c >> 6);
      buf[n++] = 0x80 | (c & 0x3f);
    } else if (c >= 0xd800 && c <= 0xdbff) {
      const lo = i + 1 < s.length ? s.charCodeAt(i + 1) : Number.NaN;
      if (!(lo >= 0xdc00 && lo <= 0xdfff)) {
        throw unpairedSurrogate("high", c, i);
      }
      const cp = 0x10000 + ((c - 0xd800) << 10) + (lo - 0xdc00);
      ensure(4);
      buf[n++] = 0xf0 | (cp >> 18);
      buf[n++] = 0x80 | ((cp >> 12) & 0x3f);
      buf[n++] = 0x80 | ((cp >> 6) & 0x3f);
      buf[n++] = 0x80 | (cp & 0x3f);
      i++;
    } else if (c >= 0xdc00 && c <= 0xdfff) {
      throw unpairedSurrogate("low", c, i);
    } else {
      ensure(3);
      buf[n++] = 0xe0 | (c >> 12);
      buf[n++] = 0x80 | ((c >> 6) & 0x3f);
      buf[n++] = 0x80 | (c & 0x3f);
    }
  }
  return buf.subarray(0, n);
}

function unpairedSurrogate(half: "high" | "low", code: number, index: number): Error {
  const point = code.toString(16).toUpperCase();
  const where = `unpaired ${half} surrogate U+${point} at index ${index}`;
  return new CanonicalizationError(`${where}; the string is not valid Unicode`);
}
