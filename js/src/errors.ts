/**
 * Errors, diagnostics, provenance, and the machine-readable code registry.
 *
 * Twin of `python/src/chiptime/errors.py`. The registries themselves are transcoded
 * into `codes.ts` and re-exported here, so this module has the same surface Python's
 * does while the 103 agent-facing strings stay in one place (ADR-0009 section 8's
 * precedent, applied to codes).
 *
 * Contract #5: every failure carries a stable code, a human sentence, and a
 * suggestion. Contract #1: every drop, repair, synthesis or reinterpretation is a
 * ProvenanceEntry. ADR-0003: decode emits Defect *values*; only the API boundary
 * raises.
 */

import { DEFECT_ERROR_KIND, type ErrorKind } from "./codes.js";

export { DEFECT_ERROR_KIND, ERROR_CODES, PROVENANCE_CODES, WARNING_CODES } from "./codes.js";
export type { ErrorKind } from "./codes.js";

export type Severity = "fatal" | "structural" | "data";
export type Action = "dropped" | "repaired" | "synthesized" | "reinterpreted" | "ignored";

/** An in-stream problem found while decoding. Never an exception (ADR-0003). */
export interface Defect {
  readonly code: string;
  readonly detail: string;
  readonly offset: number;
  readonly severity: Severity;
}

/** A non-fatal observation surfaced to the user (`warnings[]`). */
export interface Diagnostic {
  readonly code: string;
  readonly detail: string;
  readonly scope: string;
}

/** A record of something chiptime dropped, repaired, synthesized, or reinterpreted. */
export interface ProvenanceEntry {
  readonly code: string;
  readonly action: Action;
  readonly scope: string;
  readonly detail: string;
  readonly byteOffset: number | null;
  readonly data: Readonly<Record<string, unknown>>;
}

export function defect(code: string, detail: string, offset: number, severity: Severity): Defect {
  return { code, detail, offset, severity };
}

export function diagnostic(code: string, detail: string, scope: string): Diagnostic {
  return { code, detail, scope };
}

export function provenance(
  code: string,
  action: Action,
  scope: string,
  detail: string,
  byteOffset: number | null = null,
  data: Readonly<Record<string, unknown>> = {},
): ProvenanceEntry {
  return { code, action, scope, detail, byteOffset, data };
}

/** Base error. In strict mode these raise; in lenient/forensic they collect. */
export class FitError extends Error {
  readonly code: string;
  readonly detail: string;
  readonly byteOffset: number | null;
  readonly suggestion: string | null;

  constructor(
    code: string,
    detail: string,
    options: { byteOffset?: number | null; suggestion?: string | null } = {},
  ) {
    const suggestion = options.suggestion ?? null;
    super(`${code}: ${detail}${suggestion ? ` — ${suggestion}` : ""}`);
    this.name = new.target.name;
    this.code = code;
    this.detail = detail;
    this.byteOffset = options.byteOffset ?? null;
    this.suggestion = suggestion;
    // Without this, `err instanceof TruncatedError` is false whenever the class is
    // compiled to a downlevel target: the prototype chain is severed by `Error`'s
    // constructor returning a fresh object. A hierarchy that silently fails to match
    // is worse than no hierarchy, because callers write the check and believe it.
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

export class NotFitError extends FitError {}
export class EmptyFileError extends FitError {}
export class HeaderError extends FitError {}
export class TruncatedError extends FitError {}
export class CrcMismatchError extends FitError {}
export class ProtocolError extends FitError {}

const ERROR_CLASSES: Readonly<
  Record<
    ErrorKind,
    new (
      code: string,
      detail: string,
      options?: { byteOffset?: number | null; suggestion?: string | null },
    ) => FitError
  >
> = {
  NotFitError,
  EmptyFileError,
  HeaderError,
  TruncatedError,
  CrcMismatchError,
  ProtocolError,
};

/** Convert a defect into the error strict mode would raise for it. */
export function defectToError(d: Defect, suggestion: string | null = null): FitError {
  const kind = DEFECT_ERROR_KIND[d.code] ?? "ProtocolError";
  const Cls = ERROR_CLASSES[kind];
  return new Cls(d.code, d.detail, { byteOffset: d.offset, suggestion });
}
