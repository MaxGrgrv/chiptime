/**
 * FIT profile: base types, plus the merged message and enum tables.
 *
 * Twin of `python/src/chiptime/profile/__init__.py`, with one structural difference.
 * Python merges here at import time -- generated SDK breadth as the base, the
 * hand-authored fitdecode-verified core overriding per field and per enum value.
 * TypeScript consumes the *result* of that merge, transcoded (ADR-0009 section 8),
 * so the policy has one implementation rather than two.
 *
 * Unknown-tolerance is unchanged and is the behavior this layer owns: anything absent
 * from these tables still decodes as `unknown_*` (contract #6). A stale profile
 * degrades; it never crashes.
 */

export type { Accessor, BaseType } from "./base-types.js";
export { BASE_TYPES, BASE_TYPES_BY_NAME, isInvalid } from "./base-types.js";
export type { FieldDef, FieldKind, MessageDef } from "./core.js";
export { SEMICIRCLE_SCALE } from "./core.js";
export { GENERATED_SDK_VERSION } from "./generated.js";

// The vendor registry is deliberately NOT re-exported here. Python reaches it as
// `chiptime.profile.registry.lookup`, not `chiptime.profile.lookup`, and the two
// surfaces mirror each other name for name (ADR-0009 section 2). Import it from
// "./registry.js".

import type { MessageDef } from "./core.js";
import { GENERATED_ENUMS, GENERATED_MESSAGES } from "./generated.js";

/** Global message number to definition. Already merged; see the module docstring. */
export const MESSAGES: Readonly<Record<number, MessageDef>> = GENERATED_MESSAGES;

/** Enum type name to value-to-label map. Already merged. */
export const ENUMS: Readonly<Record<string, Readonly<Record<number, string>>>> = GENERATED_ENUMS;
