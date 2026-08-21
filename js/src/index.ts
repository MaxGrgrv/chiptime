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
export { iterFrames, iterMessages } from "./api.js";
export {
  CrcMismatchError,
  EmptyFileError,
  FitError,
  HeaderError,
  NotFitError,
  ProtocolError,
  TruncatedError,
} from "./errors.js";
