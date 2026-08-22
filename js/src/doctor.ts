/**
 * Why won't this file upload, and what should I run?
 *
 * Twin of `python/src/chiptime/doctor.py` (F29). The join between validate and
 * the fixing verbs: one command that reads a stubborn file and prints what is
 * wrong, who cares, and **the exact command that fixes it** — the "errors are
 * written for agents" contract applied to a whole file, for humans.
 */

import { type Mode, parse } from "./api.js";
import { type Session, recordCount } from "./model.js";
import { pyFixed } from "./numeric.js";
import { type Finding, type Platform, validate } from "./validate.js";

/** A concrete next step, not a hint. */
export interface Remedy {
  /** The command to run, ready to paste. */
  readonly command: string;
  /** Why this fixes the findings it covers. */
  readonly reason: string;
  /** The finding codes this remedy resolves. */
  readonly codes: readonly string[];
  /** Lower runs first (structural repair before cosmetics). */
  readonly priority: number;
}

/** What a platform will make of this file, and what to do about it. */
export class Diagnosis {
  /** The profile the verdict is against. */
  platform: string;
  /** True when nothing blocking was found. */
  willUpload: boolean;
  /** Findings that will cause rejection. */
  blocking: Finding[] = [];
  /** Findings worth knowing that should not block. */
  advisory: Finding[] = [];
  /** Ordered, deduplicated next steps. */
  remedies: Remedy[] = [];
  /** Blocking findings with no known automatic fix. */
  unresolved: Finding[] = [];
  /** One-line description of the parse itself. */
  summary = "";

  constructor(platform: string, willUpload: boolean) {
    this.platform = platform;
    this.willUpload = willUpload;
  }

  toDict(): Record<string, unknown> {
    return {
      platform: this.platform,
      will_upload: this.willUpload,
      blocking: this.blocking.map((f) => ({ code: f.code, detail: f.detail })),
      advisory: this.advisory.map((f) => ({ code: f.code, detail: f.detail })),
      remedies: this.remedies.map((r) => ({
        command: r.command,
        reason: r.reason,
        codes: [...r.codes],
      })),
      unresolved: this.unresolved.map((f) => ({ code: f.code, detail: f.detail })),
      summary: this.summary,
    };
  }
}

// Finding code → how to fix it. Deliberately small: a remedy table that
// prescribes something which does not work is worse than saying "I don't
// know", so every entry here is exercised by a test that runs the command
// and re-validates.
const REPAIR_CODES = [
  "VAL_GC_NO_SESSION",
  "VAL_GC_NO_ACTIVITY",
  "VAL_GC_NO_LAP",
  "VAL_GC_NO_FILE_ID",
  "VAL_GC_NO_TIME_CREATED",
  "VAL_GC_NO_MANUFACTURER",
  "VAL_GC_NO_EVENTS",
  "VAL_GC_NO_TIMER_STOP",
  "VAL_GC_LOCAL_TIMESTAMP",
  "VAL_GC_NONMONOTONIC_SOURCE",
  "VAL_STRAVA_NO_SESSION",
  "VAL_STRAVA_NO_RECORDS",
  "VAL_SPEC_NO_FILE_ID",
] as const;

/** Map findings to commands; return the remedies and the codes covered. */
function remediesFor(codes: Set<string>, srcName: string): [Remedy[], Set<string>] {
  const remedies: Remedy[] = [];
  const covered = new Set<string>();

  const repairable = REPAIR_CODES.filter((c) => codes.has(c)).sort();
  if (repairable.length > 0) {
    remedies.push({
      command: `chiptime repair ${srcName} -o fixed.fit`,
      reason:
        "rebuilds the structure platforms require (file identity, timer events, " +
        "session/lap/activity summaries) from the data that is actually there",
      codes: repairable,
      priority: 10,
    });
    for (const c of repairable) covered.add(c);
  }

  if (codes.has("VAL_GC_NOT_ACTIVITY")) {
    remedies.push({
      command: `chiptime parse ${srcName}`,
      reason:
        "this is not an activity file, so an activity upload will never accept it; " +
        "check what it actually is",
      codes: ["VAL_GC_NOT_ACTIVITY"],
      priority: 20,
    });
    covered.add("VAL_GC_NOT_ACTIVITY");
  }

  if (codes.has("VAL_GC_CORRUPTION_GAPS")) {
    remedies.push({
      command: `chiptime repair ${srcName} -o fixed.fit --mode forensic`,
      reason:
        "the file has corruption gaps; forensic salvage recovers the most it can " +
        "and records exactly what was skipped",
      codes: ["VAL_GC_CORRUPTION_GAPS"],
      priority: 15,
    });
    covered.add("VAL_GC_CORRUPTION_GAPS");
  }

  remedies.sort((a, b) =>
    a.priority !== b.priority ? a.priority - b.priority : a.command < b.command ? -1 : 1,
  );
  return [remedies, covered];
}

export interface DoctorOptions {
  /** Which platform's observed rules to judge against. */
  platform?: Platform;
  /** Parse policy for reading the input. */
  mode?: Mode;
  /** Name used in prescribed commands. Python's `doctor` sees the file *path*
   * and embeds it; a byte source prints as "FILE" on both sides. */
  srcName?: string;
}

/**
 * Diagnose why a platform will refuse a file, and prescribe the fix.
 *
 * Returns a `Diagnosis` with blocking findings, advisory findings, ordered
 * remedies, and any blocking finding for which chiptime has no automatic fix
 * (named honestly rather than papered over).
 */
export function doctor(src: Uint8Array, options: DoctorOptions = {}): Diagnosis {
  const platform = options.platform ?? "garmin-connect";
  const mode = options.mode ?? "lenient";
  const name = options.srcName ?? "FILE";

  const parsed = parse(src, { mode });
  const findings = validate(src, platform);
  const blocking = findings.filter((f) => f.level === "error");
  const advisory = findings.filter((f) => f.level !== "error");

  const [remedies, covered] = remediesFor(new Set(findings.map((f) => f.code)), name);
  const unresolved = blocking.filter((f) => !covered.has(f.code));

  const bits = [`parse ${parsed.ok ? "ok" : "FAILED"}`];
  const activity = parsed.activity as { sessions: Session[] } | null;
  if (activity !== null && activity.sessions !== undefined && activity.sessions.length > 0) {
    const session = activity.sessions[0] as Session;
    bits.push(`${recordCount(session.records)} records`);
    // Python truthiness: a zero distance is not reported.
    if (session.derived.distanceM) {
      bits.push(`${pyFixed(session.derived.distanceM / 1000, 2)} km`);
    }
    if (session.discrepancies.length > 0) {
      bits.push(`${session.discrepancies.length} declared-vs-derived discrepancies`);
    }
  }
  if (parsed.recovery !== null) {
    bits.push(`${parsed.recovery.recoveredRecords} messages recovered`);
  }

  const d = new Diagnosis(String(platform), blocking.length === 0);
  d.blocking = blocking;
  d.advisory = advisory;
  d.remedies = remedies;
  d.unresolved = unresolved;
  d.summary = bits.join(" · ");
  return d;
}
