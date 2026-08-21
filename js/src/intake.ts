/**
 * Intake: container unwrapping and content sniffing (taxonomy #14, #15).
 *
 * Twin of `python/src/chiptime/intake.py`. Runs before frame decoding. Never
 * throws; returns typed defects (ADR-0003).
 */

import { type Defect, type ProvenanceEntry, defect } from "./errors.js";
import { gunzip, readZipEntries } from "./inflate.js";

export const MAX_UNWRAP_DEPTH = 3;

const GZIP_MAGIC = [0x1f, 0x8b];
const ZIP_MAGIC = [0x50, 0x4b, 0x03, 0x04];

export interface IntakeResult {
  data: Uint8Array;
  unwrapped: string[];
  defects: Defect[];
  provenance: ProvenanceEntry[];
}

function startsWith(data: Uint8Array, magic: number[]): boolean {
  if (data.length < magic.length) return false;
  for (let i = 0; i < magic.length; i++) if (data[i] !== magic[i]) return false;
  return true;
}

const LATIN1 = new TextDecoder("utf-8");

/** Peel containers, then sniff for non-FIT content. */
export function unwrap(data: Uint8Array): IntakeResult {
  const result: IntakeResult = { data, unwrapped: [], defects: [], provenance: [] };
  for (let depth = 0; depth < MAX_UNWRAP_DEPTH; depth++) {
    if (startsWith(result.data, GZIP_MAGIC)) {
      const out = gunzip(result.data);
      if (!out.ok) {
        result.defects.push(
          defect("NOT_FIT_FORMAT", `gzip container failed to decompress: ${out.error}`, 0, "fatal"),
        );
        return result;
      }
      result.data = out.data;
      result.unwrapped.push("gzip");
      continue;
    }
    if (startsWith(result.data, ZIP_MAGIC)) {
      if (!unzip(result)) return result;
      continue;
    }
    break;
  }

  if (fitPlausible(result.data)) return result;
  const looks = sniff(result.data);
  if (looks !== null) {
    result.defects.push(defect("NOT_FIT_FORMAT", `content is ${looks}`, 0, "fatal"));
  }
  // Unrecognized bytes fall through to the frame reader -- its defects
  // (FIT_EMPTY / FIT_TOO_SMALL / NOT_FIT_FORMAT) are more precise than a guess.
  return result;
}

function unzip(result: IntakeResult): boolean {
  const entries = readZipEntries(result.data);
  const fits = entries.filter((e) => e.name.toLowerCase().endsWith(".fit"));
  if (entries.length === 0) {
    result.defects.push(defect("NOT_FIT_FORMAT", "zip container failed to read", 0, "fatal"));
    return false;
  }
  if (fits.length === 0) {
    result.defects.push(
      defect("NOT_FIT_FORMAT", "zip archive contains no .fit entries", 0, "fatal"),
    );
    return false;
  }
  // Python sorts by name and concatenates; the order is part of the output.
  fits.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
  let total = 0;
  for (const e of fits) total += e.data.length;
  const joined = new Uint8Array(total);
  let at = 0;
  for (const e of fits) {
    joined.set(e.data, at);
    at += e.data.length;
  }
  result.data = joined;
  result.unwrapped.push("zip");
  if (fits.length > 1) {
    // Multiple .fit entries become the legal chained form (taxonomy #12).
    result.provenance.push({
      code: "ZIP_ENTRIES_CHAINED",
      action: "reinterpreted",
      scope: "intake",
      detail: `${fits.length} .fit entries from the zip parsed as chained parts`,
      byteOffset: null,
      data: { entries: fits.map((e) => e.name) },
    });
  }
  return true;
}

/** Cheap positive check: plausible header-size byte or the `.FIT` magic. */
function fitPlausible(data: Uint8Array): boolean {
  if (data.length < 12) return true; // let the frame reader report precisely
  const magic = data[8] === 0x2e && data[9] === 0x46 && data[10] === 0x49 && data[11] === 0x54;
  return magic || data[0] === 12 || data[0] === 14;
}

function sniff(data: Uint8Array): string | null {
  // Python lstrips a BOM and leading whitespace before looking.
  const head = data.subarray(0, 512);
  let start = 0;
  const strip = [0xef, 0xbb, 0xbf, 0x20, 0x09, 0x0d, 0x0a];
  while (start < head.length && strip.includes(head[start] as number)) start++;
  const body = head.subarray(start);
  if (body.length === 0) return null;
  const text = LATIN1.decode(body);
  const lower = text.toLowerCase();
  if (text.startsWith("<")) {
    if (lower.includes("<gpx")) return "GPX (XML with <gpx> root)";
    if (lower.includes("<trainingcenterdatabase")) {
      return "TCX (XML with <TrainingCenterDatabase> root)";
    }
    if (lower.includes("<!doctype html") || lower.includes("<html")) {
      return "an HTML page (likely a failed-download error page)";
    }
    return "XML (neither GPX nor TCX)";
  }
  if (text.startsWith("{") || text.startsWith("[")) return "JSON";
  const sample = body.subarray(0, 256);
  if (sample.length > 0) {
    let allText = true;
    for (const b of sample) {
      if (!((b >= 0x09 && b <= 0x7e) || b === 0x0a || b === 0x0d)) {
        allText = false;
        break;
      }
    }
    if (allText) return "plain text";
  }
  return null;
}
