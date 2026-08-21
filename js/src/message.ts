/**
 * Decoded message types -- the lossless middle layer between wire and semantics.
 *
 * Twin of `python/src/chiptime/message.py`. Defined here at F33 because the frame
 * reader and the registries reference the shapes; F34's decoder is what populates
 * them.
 */

import type { DefinitionFrame } from "./frames.js";

/** Where a developer field came from (resolved in F34, mirroring Python's F6). */
export interface DevFieldOrigin {
  readonly developerDataIndex: number;
  readonly fieldDefinitionNumber: number;
  /** Hex, from `developer_data_id`. */
  readonly applicationId: string | null;
  /** Manufacturer name, e.g. "stryd". */
  readonly vendor: string | null;
  /** Registry promotion for stream naming. */
  readonly canonicalName: string | null;
}

/**
 * One decoded field.
 *
 * `value` is scaled and unit-normalized with sentinels resolved to `null`; `raw` is
 * the wire value, kept for round-trips and `includeRaw` output. A 64-bit field
 * carries `bigint` in both positions (ADR-0009 section 4).
 */
export interface FieldValue {
  readonly value: unknown;
  readonly raw: unknown;
  readonly units: string | null;
  readonly developer: DevFieldOrigin | null;
}

/** A decoded FIT data message, unknown-tolerant (contract #6). */
export interface Message {
  readonly globalNum: number;
  readonly name: string;
  readonly localId: number;
  readonly byteOffset: number;
  /**
   * Keyed by field name. A `Map` rather than an object because insertion order is
   * wire order here and the decoder walks it -- unlike the profile lookup tables,
   * where order is explicitly meaningless (ADR-0009 section 8).
   */
  readonly fields: Map<string, FieldValue>;
  /** Retained for lossless re-encoding (ADR-0006). */
  readonly wire: DefinitionFrame | null;
}

/** `msg.get(name)` in Python. Returns the scaled value, or `null` when absent. */
export function get(msg: Message, name: string): unknown {
  return msg.fields.get(name)?.value ?? null;
}

/** `msg.get_raw(name)` in Python. Returns the wire value, or `null` when absent. */
export function getRaw(msg: Message, name: string): unknown {
  return msg.fields.get(name)?.raw ?? null;
}
