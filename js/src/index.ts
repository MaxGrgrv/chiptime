/**
 * chiptime — recovery-grade FIT file processing.
 *
 * Parse anything, lose nothing silently, explain everything.
 *
 * The parsing surface arrives at F34/F35 (see docs/m3-typescript-plan.md). What is
 * exported today is the determinism contract itself: the canonical serializer that
 * defines "byte-identical output" for this implementation.
 */

// Every name here has a `chiptime.canonical` counterpart in Python (ADR-0009 §2:
// one name per concept, and no concept the twin does not have). `dumpsText` is
// deliberately absent — it is a test and diagnostic convenience with no Python
// analogue, and stays importable from the module rather than from the package.
export { CanonicalizationError, MAX_SAFE_INT, dumps, formatNumber } from "./canonical.js";
