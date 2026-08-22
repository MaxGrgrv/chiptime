/**
 * Platform validation profiles (taxonomy #99/#102).
 *
 * Twin of `python/src/chiptime/validate.py`. Folk knowledge encoded as explicit
 * checks — heuristic by nature, named and versioned in the open so corrections are
 * one-line PRs, not tribal lore.
 */

import { parse } from "./api.js";
import { FitError } from "./errors.js";
import type { Activity } from "./model.js";
import type { ParseResult } from "./result.js";

export type Platform = "strict-spec" | "garmin-connect" | "strava";
export type Level = "error" | "warning";

/** One platform-acceptance issue: severity, a stable code, and the human reason. */
export interface Finding {
  readonly level: Level;
  readonly code: string;
  readonly detail: string;
}

export function validate(src: Uint8Array, platform: Platform = "strict-spec"): Finding[] {
  if (platform === "strict-spec") return strictSpec(src);
  const result = parse(src);
  if (!result.ok) {
    return [
      {
        level: "error",
        code: "VAL_UNPARSEABLE",
        detail: "file does not parse; run chiptime parse for details",
      },
    ];
  }
  return platform === "garmin-connect" ? garminConnect(result) : strava(result);
}

function strictSpec(src: Uint8Array): Finding[] {
  let result: ParseResult;
  try {
    result = parse(src, { mode: "strict" });
  } catch (e) {
    if (e instanceof FitError) {
      return [{ level: "error", code: "VAL_SPEC_VIOLATION", detail: `${e.code}: ${e.detail}` }];
    }
    throw e;
  }
  if (!result.ok) {
    return [{ level: "error", code: "VAL_SPEC_VIOLATION", detail: "no usable content" }];
  }
  return [];
}

/** Documented GC rejection classes (#99): stricter than Strava. */
function garminConnect(result: ParseResult): Finding[] {
  const out: Finding[] = [];
  const part = result.parts[0];
  const fid = part?.fileId ?? null;
  if (fid === null) {
    out.push({ level: "error", code: "VAL_GC_NO_FILE_ID", detail: "file_id message missing" });
  } else {
    const type = fid.get("type") ?? null;
    if (type !== "activity") {
      out.push({
        level: "error",
        code: "VAL_GC_NOT_ACTIVITY",
        detail: `file_id.type is ${pyRepr(type)}, not 'activity'`,
      });
    }
    if ((fid.get("time_created") ?? null) === null) {
      out.push({
        level: "error",
        code: "VAL_GC_NO_TIME_CREATED",
        detail: "file_id.time_created missing",
      });
    }
    if ((fid.get("manufacturer") ?? null) === null) {
      out.push({
        level: "error",
        code: "VAL_GC_NO_MANUFACTURER",
        detail: "file_id.manufacturer missing",
      });
    }
  }
  const names = new Set(result.messages.map((m) => m.name));
  const needs: [string, string][] = [
    ["session", "VAL_GC_NO_SESSION"],
    ["activity", "VAL_GC_NO_ACTIVITY"],
    ["lap", "VAL_GC_NO_LAP"],
  ];
  for (const [need, code] of needs) {
    if (!names.has(need)) {
      out.push({ level: "error", code, detail: `no ${need} message (GC requires one)` });
    }
  }
  if (!names.has("event")) {
    out.push({
      level: "warning",
      code: "VAL_GC_NO_EVENTS",
      detail: "no timer events; GC usually tolerates but flags this",
    });
  }
  const a = result.activity as Activity | null;
  if (a !== null && a.sessions.length > 0) {
    if (a.gaps.some((g) => g.kind === "corruption")) {
      out.push({
        level: "warning",
        code: "VAL_GC_CORRUPTION_GAPS",
        detail: "corruption gaps present; GC may truncate the activity",
      });
    }
    if (result.provenance.some((pv) => pv.code === "RECORDS_REORDERED")) {
      out.push({
        level: "warning",
        code: "VAL_GC_NONMONOTONIC_SOURCE",
        detail:
          "source records were out of order (GC rejects non-monotonic files; a chiptime repair re-emits sorted)",
      });
    }
  }
  const events = (part?.messages ?? []).filter((m) => m.name === "event");
  if (
    events.length > 0 &&
    !events.some((m) => String(m.fields.get("event_type")?.value ?? "").includes("stop"))
  ) {
    out.push({
      level: "warning",
      code: "VAL_GC_NO_TIMER_STOP",
      detail:
        "activity has timer events but never a stop; Garmin Connect is reported to require a stop event (community-observed, not documented)",
    });
  }
  if (result.warnings.some((w) => w.code === "LOCAL_TIMESTAMP_IMPLAUSIBLE")) {
    out.push({
      level: "error",
      code: "VAL_GC_LOCAL_TIMESTAMP",
      detail:
        "implausible local_timestamp — the documented Zwift rejection class (#37); repair omits it",
    });
  }
  return out;
}

function strava(result: ParseResult): Finding[] {
  const out: Finding[] = [];
  const part = result.parts[0];
  const fid = part?.fileId ?? null;
  if (fid === null || (fid.get("type") ?? null) !== "activity") {
    out.push({
      level: "error",
      code: "VAL_STRAVA_NOT_ACTIVITY",
      detail: "file_id.type=activity required",
    });
  }
  const a = result.activity as Activity | null;
  let n = 0;
  if (a !== null) for (const s of a.sessions) n += s.records.time.length;
  if (n === 0) {
    out.push({
      level: "error",
      code: "VAL_STRAVA_NO_RECORDS",
      detail: "no records; Strava needs a timeline",
    });
  }
  if (a !== null && !a.sessions.some((s) => !s.rebuilt)) {
    out.push({
      level: "warning",
      code: "VAL_STRAVA_NO_SESSION",
      detail: "no session message; Strava usually accepts but computes its own totals",
    });
  }
  return out;
}

/** Python's `{v!r}` for the values that appear here: strings quoted, None as None. */
function pyRepr(v: unknown): string {
  if (v === null || v === undefined) return "None";
  if (typeof v === "string") return `'${v}'`;
  return String(v);
}
