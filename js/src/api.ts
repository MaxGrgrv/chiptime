/**
 * The public entry points.
 *
 * Twin of `python/src/chiptime/_api.py`, arriving one verb at a time: `iterFrames`
 * here at F33, `iterMessages` at F34, `parse` at F35 when intake and result shaping
 * exist.
 */

import { defectToError } from "./errors.js";
import { type FrameEvent, readStream } from "./frames.js";

export type Mode = "strict" | "lenient" | "forensic";

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
