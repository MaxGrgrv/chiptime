/**
 * The public entry points.
 *
 * Twin of `python/src/chiptime/_api.py`, arriving one verb at a time: `iterFrames`
 * here at F33, `iterMessages` at F34, `parse` at F35 when intake and result shaping
 * exist.
 */

import { Decoder } from "./decode.js";
import {
  type Defect,
  type Diagnostic,
  FitError,
  type ProvenanceEntry,
  defect,
  defectToError,
} from "./errors.js";
import { type FileHeader, type FrameEvent, type SkippedBytes, readStream } from "./frames.js";
import { unwrap } from "./intake.js";
import type { Message } from "./message.js";
import { pyRound } from "./numeric.js";
import { type FitPart, type Mode, ParseResult, type SourceInfo } from "./result.js";
import { buildActivity } from "./semantics/build.js";
import { sha256Hex } from "./sha256.js";

export type { Mode } from "./result.js";

/**
 * What to tell an agent to do next, per defect code (contract #5).
 *
 * Mirrors `_SUGGESTIONS` in `_api.py`. Not in the generated `codes.ts`: these belong
 * to the API boundary that raises, not to the registry that names things, and Python
 * keeps them in the same place for the same reason.
 */
const SUGGESTIONS: Readonly<Record<string, string>> = {
  NOT_FIT_FORMAT: "route this file to a parser for the named format",
  FIT_TRUNCATED: 'rerun with mode="lenient" to salvage the decodable prefix',
  FIT_CRC_MISMATCH: 'rerun with mode="lenient" to decode despite the bad CRC',
  FIT_HEADER_CRC_MISMATCH: 'rerun with mode="lenient" to decode despite the bad header CRC',
  FIT_UNDEFINED_LOCAL_TYPE: 'rerun with mode="lenient" to salvage the decodable prefix',
  FIT_DEFINITION_INVALID: 'rerun with mode="lenient" to salvage the decodable prefix',
  FIT_DATA_SIZE_MISMATCH: 'rerun with mode="lenient" to parse the actual content',
};

function looksLikeHeader(data: Uint8Array, offset: number): boolean {
  if (data.length - offset < 12) return false;
  const magic =
    data[offset + 8] === 0x2e &&
    data[offset + 9] === 0x46 &&
    data[offset + 10] === 0x49 &&
    data[offset + 11] === 0x54;
  return magic || data[offset] === 12 || data[offset] === 14;
}

/**
 * Lossless wire-level frame events (forensics layer) — `chiptime inspect`'s source.
 *
 * This is the chained-file loop, not a thin pass-through to `readStream`. Two
 * behaviors live here rather than in the reader, and both are observable:
 *
 *   - A zero-length input yields **nothing**. The `while` never runs, so the reader's
 *     `FIT_EMPTY` defect is never reached — an empty file is the caller's problem to
 *     report, and `parse()` does (taxonomy #1).
 *   - Chained files (taxonomy #12) continue from `EndOfStream.consumed` for as long
 *     as what follows still looks like a header.
 *
 * `strict` raises the first defect; `lenient` and `forensic` yield everything and
 * leave the policy to the caller.
 *
 * Input is `Uint8Array` at this stage; path and stream inputs arrive with intake.
 */
export function* iterFrames(src: Uint8Array, options: { mode?: Mode } = {}): Generator<FrameEvent> {
  const mode = options.mode ?? "lenient";
  let offset = 0;
  while (offset < src.length) {
    let consumed = offset;
    for (const ev of readStream(src, { offset })) {
      if (ev.kind === "defect" && mode === "strict") {
        throw defectToError(ev, SUGGESTIONS[ev.code] ?? null);
      }
      if (ev.kind === "eos") consumed = ev.consumed;
      yield ev;
    }
    if (consumed <= offset || !looksLikeHeader(src, consumed)) break;
    offset = consumed;
  }
}

/**
 * Profile-applied message stream without building the semantic model.
 *
 * Mirrors `iter_messages`: `iterFrames` filtered to data frames through one
 * `Decoder`. Note that Python never calls `finish()` here either, so diagnostics,
 * provenance and late-resolved developer fields are NOT observable through this
 * generator — they reach users at F35 through `parse()`. Construct a `Decoder`
 * directly when you need them.
 */
export function* iterMessages(src: Uint8Array, options: { mode?: Mode } = {}): Generator<Message> {
  const decoder = new Decoder();
  for (const ev of iterFrames(src, options)) {
    if (ev.kind === "data") yield decoder.decode(ev);
  }
}

// ── parse ─────────────────────────────────────────────────────────────────

/**
 * Defect codes that are survivable: they become warnings and decoding continues,
 * rather than stopping the stream. Mirrors `_CONTINUE_CODES` in `_api.py`.
 */
const CONTINUE_CODES = new Set([
  "FIT_HEADER_INVALID",
  "FIT_HEADER_CRC_MISMATCH",
  "FIT_CRC_MISMATCH",
  "FIT_CRC_MISSING",
  "FIT_DATA_SIZE_MISMATCH",
]);

const PII_MESSAGES = new Set(["user_profile"]);
const PII_FIELDS = ["serial_number"];

export interface ParseOptions {
  mode?: Mode;
  stripPii?: boolean;
  includeUnknown?: boolean;
  includeRaw?: boolean;
}

function buildPart(messages: Message[]): FitPart {
  let fileId: Map<string, unknown> | null = null;
  let fileType = "unknown";
  for (const m of messages) {
    if (m.globalNum === 0) {
      fileId = new Map([...m.fields].map(([k, fv]) => [k, fv.value]));
      const t = m.fields.get("type")?.value ?? null;
      if (typeof t === "string") fileType = t;
      else if (t !== null) fileType = `unknown_${String(t)}`;
      break;
    }
  }
  return { fileType, fileId, messages, activity: null };
}

function stripPiiFrom(part: FitPart, provenance: ProvenanceEntry[], scope: string): void {
  let removedMsgs = 0;
  let nulledFields = 0;
  const kept: Message[] = [];
  for (const m of part.messages) {
    if (PII_MESSAGES.has(m.name)) {
      removedMsgs += 1;
      continue;
    }
    if (PII_FIELDS.some((f) => m.fields.has(f))) {
      const fields = new Map(m.fields);
      for (const f of PII_FIELDS) {
        const existing = fields.get(f);
        if (existing !== undefined) {
          fields.set(f, { value: null, raw: null, units: existing.units, developer: null });
          nulledFields += 1;
        }
      }
      kept.push({ ...m, fields });
      continue;
    }
    kept.push(m);
  }
  part.messages = kept;
  if (part.fileId?.has("serial_number")) part.fileId.set("serial_number", null);
  if (removedMsgs || nulledFields) {
    provenance.push({
      code: "PII_STRIPPED",
      action: "dropped",
      scope,
      detail: `removed ${removedMsgs} PII message(s), nulled ${nulledFields} serial-number field(s) (strip_pii=True)`,
      byteOffset: null,
      data: { messages_removed: removedMsgs, fields_nulled: nulledFields },
    });
  }
}

function dropUnknown(part: FitPart, provenance: ProvenanceEntry[], scope: string): void {
  const known = part.messages.filter((m) => !m.name.startsWith("unknown_"));
  const dropped = part.messages.length - known.length;
  part.messages = known;
  if (dropped) {
    provenance.push({
      code: "UNKNOWN_MESSAGES_OMITTED",
      action: "ignored",
      scope,
      detail: `${dropped} unknown message(s) omitted from output (include_unknown=False)`,
      byteOffset: null,
      data: { count: dropped },
    });
  }
}

/**
 * Parse a FIT source.
 *
 * `lenient` (default) recovers and annotates; `strict` raises the first
 * `FitError`; `forensic` maximizes salvage and never drops.
 *
 * Input is `Uint8Array`. Path input arrives with the CLI, which is where a
 * filesystem exists — keeping `node:fs` out of this module is what lets the
 * package load in a browser.
 */
export function parse(src: Uint8Array, options: ParseOptions = {}): ParseResult {
  const mode: Mode = options.mode ?? "lenient";
  const stripPii = options.stripPii ?? false;
  const includeUnknown = options.includeUnknown ?? true;
  const includeRaw = options.includeRaw ?? false;

  const raw = src;
  const sourceHash = sha256Hex(raw);
  const intake = unwrap(raw);
  const data = intake.data;
  const source: SourceInfo = {
    path: null,
    sizeBytes: raw.length,
    sha256: sourceHash,
    unwrapped: intake.unwrapped,
  };

  const parts: FitPart[] = [];
  const provenance: ProvenanceEntry[] = [...intake.provenance];
  const warnings: Diagnostic[] = [];
  const errors: FitError[] = [];

  for (const d of intake.defects) {
    const err = defectToError(d, SUGGESTIONS[d.code] ?? null);
    if (mode === "strict") throw err;
    errors.push(err);
  }
  if (intake.defects.some((d) => d.severity === "fatal")) {
    return new ParseResult({
      ok: false,
      mode,
      source,
      parts: [],
      provenance,
      warnings,
      errors,
      recovery: null,
      includeRaw,
    });
  }

  let totalRecovered = 0;
  let totalSkipped = 0;
  let resyncCount = 0;
  let recoveryEngaged = false;
  let estTotal: number | null = null;

  let offset = 0;
  let partIndex = 0;
  for (;;) {
    const decoder = new Decoder();
    let messages: Message[] = [];
    const streamDefects: Defect[] = [];
    const skips: SkippedBytes[] = [];
    let header: FileHeader | null = null;
    let consumed = data.length;
    let bodyBytesDecoded = 0;

    for (const ev of readStream(data, { offset })) {
      if (ev.kind === "defect") {
        if (mode === "strict") throw defectToError(ev, SUGGESTIONS[ev.code] ?? null);
        streamDefects.push(ev);
      } else if (ev.kind === "skipped") {
        skips.push(ev);
      } else if (ev.kind === "data") {
        messages.push(decoder.decode(ev));
        bodyBytesDecoded =
          ev.offset + 1 + ev.payload.length - (header ? header.offset + header.size : offset);
      } else if (ev.kind === "header") {
        header = ev;
      } else if (ev.kind === "eos") {
        consumed = ev.consumed;
      }
    }

    const decodeOut = decoder.finish();
    messages = decodeOut.messages; // finish() may rebuild (late dev-field back-fill)
    provenance.push(...decodeOut.provenance);
    warnings.push(...decodeOut.diagnostics);
    for (const d of decodeOut.defects) {
      if (mode === "strict") throw defectToError(d, SUGGESTIONS[d.code] ?? null);
      warnings.push({ code: d.code, detail: d.detail, scope: `byte ${d.offset}` });
    }

    const scope = `part[${partIndex}]`;
    const skipOffsets = new Set(skips.map((s) => s.offset));
    for (const skip of skips) {
      recoveryEngaged = true;
      totalSkipped += skip.length;
      if (skip.reason === "preamble-garbage") {
        provenance.push({
          code: "PREAMBLE_GARBAGE_SKIPPED",
          action: "repaired",
          scope,
          detail: `skipped ${skip.length} garbage byte(s) before the FIT header`,
          byteOffset: skip.offset,
          data: { length: skip.length },
        });
      } else {
        resyncCount += 1;
        provenance.push({
          code: "RESYNC_SKIPPED_BYTES",
          action: "repaired",
          scope,
          detail: `skipped ${skip.length} undecodable byte(s) after ${skip.reason} at offset ${skip.offset}; decoding resumed`,
          byteOffset: skip.offset,
          data: { length: skip.length, defect_code: skip.reason },
        });
      }
    }
    for (const d of streamDefects) {
      if (skipOffsets.has(d.offset) && d.severity === "structural") continue;
      if (d.severity === "fatal") {
        errors.push(defectToError(d, SUGGESTIONS[d.code] ?? null));
      } else if (CONTINUE_CODES.has(d.code)) {
        warnings.push({ code: d.code, detail: d.detail, scope: `byte ${d.offset}` });
      } else {
        recoveryEngaged = true;
        const code =
          d.code === "FIT_TRUNCATED" ? "TRUNCATED_TAIL_SALVAGED" : "STREAM_STOPPED_AT_DEFECT";
        provenance.push({
          code,
          action: "repaired",
          scope,
          detail: `${d.detail}; salvaged ${messages.length} complete message(s)`,
          byteOffset: d.offset,
          data: { defect_code: d.code },
        });
        if (
          d.code === "FIT_TRUNCATED" &&
          header !== null &&
          header.dataSize &&
          bodyBytesDecoded > 0
        ) {
          // Python's round() is half-to-even, and this lands in canonical output.
          estTotal = pyRound((messages.length * header.dataSize) / bodyBytesDecoded);
        }
      }
    }

    if (messages.length > 0 || header !== null) {
      const part = buildPart(messages);
      if (stripPii) stripPiiFrom(part, provenance, scope);
      if (!includeUnknown) dropUnknown(part, provenance, scope);
      if (part.fileType === "activity") {
        part.activity = buildActivity(part.messages, warnings, provenance, scope, {
          skippedRanges: skips.map((sk) => [sk.offset, sk.offset + sk.length]),
          forensic: mode === "forensic",
        });
      }
      parts.push(part);
      totalRecovered += messages.length;
    }

    partIndex += 1;
    if (consumed <= offset) break;
    offset = consumed;
    if (offset >= data.length) break;
    if (!looksLikeHeader(data, offset)) {
      const junk = defect(
        "FIT_TRAILING_JUNK",
        `${data.length - offset} byte(s) after the final CRC are not a chained FIT file`,
        offset,
        "structural",
      );
      if (mode === "strict") throw defectToError(junk);
      if (!streamDefects.some((d) => d.severity === "structural" && !CONTINUE_CODES.has(d.code))) {
        warnings.push({ code: junk.code, detail: junk.detail, scope: `byte ${offset}` });
      }
      break;
    }
  }

  const fatalCodes = new Set(["FIT_EMPTY", "FIT_TOO_SMALL", "NOT_FIT_FORMAT"]);
  const ok =
    parts.some((p) => p.messages.length > 0) && !errors.some((e) => fatalCodes.has(e.code));
  if (!ok && errors.length === 0) {
    // Contract #5: ok=false must always be explained. The valid-but-empty shell
    // (taxonomy #16, seen in the wild as 16-byte tool output).
    errors.push(
      new FitError(
        "FIT_NO_CONTENT",
        "structurally valid FIT container with no messages — the data is genuinely absent, not recoverable",
        { suggestion: "nothing to salvage; check the device/app that wrote it" },
      ),
    );
  }

  return new ParseResult({
    ok,
    mode,
    source,
    parts,
    provenance,
    warnings,
    errors,
    recovery: recoveryEngaged
      ? {
          recoveredRecords: totalRecovered,
          estimatedTotalRecords: estTotal,
          bytesRead: data.length,
          bytesSkipped: totalSkipped,
          resyncCount,
        }
      : null,
    includeRaw,
  });
}
