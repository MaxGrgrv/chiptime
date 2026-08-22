/**
 * chiptime — recovery-grade FIT file processing.
 *
 * Parse anything, lose nothing silently, explain everything.
 *
 * This module mirrors `chiptime/__init__.py`'s `__all__` and nothing more. Names
 * Python reaches through a submodule — `chiptime.canonical.dumps`,
 * `chiptime.errors.ERROR_CODES`, `chiptime.frames.crc16` — are reached here through
 * the matching subpath export (`chiptime/canonical`, `chiptime/errors`,
 * `chiptime/frames`, `chiptime/profile`), so the two packages have the same names at
 * the same addresses (ADR-0009 section 2).
 *
 * The surface grows one verb at a time as the port climbs: `iterFrames` at F33,
 * `iterMessages` at F34, `parse` at F35.
 */

export type { Mode } from "./api.js";
export { iterFrames, iterMessages, parse } from "./api.js";
export type { ParseOptions } from "./api.js";
export type { FitPart, RecoveryReport, SourceInfo } from "./result.js";
export { ParseResult } from "./result.js";
export type { RepairResult } from "./repair.js";
export { NotRepairableError, repair } from "./repair.js";
// `validate` stays at chiptime/validate: Python's __all__ does not hoist it.
export {
  CrcMismatchError,
  EmptyFileError,
  FitError,
  HeaderError,
  NotFitError,
  ProtocolError,
  TruncatedError,
} from "./errors.js";
export type { EditOptions, EditResult } from "./edit.js";
export { EditError, edit } from "./edit.js";
export type { TrimOptions, TrimResult } from "./trim.js";
export { TrimError, trim } from "./trim.js";
export type { PrivacyFinding, ScrubOptions, ScrubResult } from "./privacy.js";
export { PrivacyReport, ScrubError, reveal, scrub } from "./privacy.js";
export type { DoctorOptions, Remedy } from "./doctor.js";
export { Diagnosis, doctor } from "./doctor.js";
