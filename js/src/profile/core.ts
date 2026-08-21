/**
 * Profile value shapes shared by the generated tables and their consumers.
 *
 * Twin of the type half of `python/src/chiptime/profile/core.py`. The hand-authored
 * message and enum tables that live alongside these types in Python are **not**
 * duplicated here: they are already folded into the merged tables that
 * `generated.ts` carries (ADR-0009 section 8).
 */

/** Semicircles to degrees (taxonomy #27). The same expression in both languages. */
export const SEMICIRCLE_SCALE = 2 ** 31 / 180.0;

/** `number | enum:<name> | date_time | local_date_time | string | bytes` */
export type FieldKind = string;

export interface FieldDef {
  readonly num: number;
  readonly name: string;
  readonly kind: FieldKind;
  readonly scale: number;
  readonly offset: number;
  readonly units: string | null;
}

export interface MessageDef {
  readonly num: number;
  readonly name: string;
  /** Keyed by field number. Iteration order is not meaningful (ADR-0009 section 8). */
  readonly fields: Readonly<Record<number, FieldDef>>;
}
