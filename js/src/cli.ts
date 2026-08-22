/**
 * chiptime CLI — agent-first exit codes and machine-readable output.
 *
 * Twin of `python/src/chiptime/cli.py`, carrying the M1 surface: `parse`,
 * `inspect`, `codes`. The remaining verbs arrive with the features that implement
 * them, exactly as they did in Python.
 *
 * Exit codes (stable contract, see docs/for-agents.md):
 *   0   parsed clean (warnings allowed)
 *   2   parsed with recovery/data loss — details in provenance
 *   3   unusable input (structurally FIT but nothing salvageable)
 *   4   not a FIT file at all
 *   64  usage error
 *
 * This is the only module that touches the filesystem, which is why `parse()` takes
 * bytes: keeping `node:fs` out of the *library* is what lets it load in a browser.
 * Importing it here is correct and deliberate — a command line implies a filesystem,
 * and nothing in `index.ts` reaches this module, so importing `chiptime` still pulls
 * in no Node builtin. The pack smoke asserts exactly that distinction.
 */

import { readFileSync, writeFileSync } from "node:fs";
import { iterFrames, parse } from "./api.js";
import { edit } from "./edit.js";
import { ERROR_CODES, FitError, NotFitError, PROVENANCE_CODES, WARNING_CODES } from "./errors.js";
import {
  type AthleteSettings,
  type WorkoutReport,
  analyze,
  dumpsReportJson,
  reportToPlain,
} from "./metrics/index.js";
import type { Session } from "./model.js";
import { pyFixed, pyFloatStr, pyG } from "./numeric.js";
import { NotRepairableError, repair } from "./repair.js";
import type { ParseResult } from "./result.js";
import { type Platform, validate } from "./validate.js";

const USAGE = `usage: chiptime [-h] {parse,inspect,repair,validate,edit,analyze,codes} ...

Recovery-grade FIT file processing.

positional arguments:
  {parse,inspect,codes}
    parse               parse a FIT file
    inspect             wire-level frame table (forensics)
    repair              salvage + synthesize + write a valid .fit
    validate            check platform acceptance (heuristic)
    analyze             per-sport workout report + insights (optional layer)
    edit                change what a file says about itself (metadata)
    codes               print the error/warning/provenance code registry
`;

type Mode = "strict" | "lenient" | "forensic";

interface ParseArgs {
  file: string;
  mode: Mode;
  json: boolean;
  output: string | null;
  stripPii: boolean;
  includeRaw: boolean;
  noUnknown: boolean;
}

class UsageError extends Error {}

function readFileBytes(path: string): Uint8Array {
  return new Uint8Array(readFileSync(path));
}

function writeFileBytes(path: string, data: Uint8Array): void {
  writeFileSync(path, data);
}

function parseArgs(argv: string[]): ParseArgs {
  const args: ParseArgs = {
    file: "",
    mode: "lenient",
    json: false,
    output: null,
    stripPii: false,
    includeRaw: false,
    noUnknown: false,
  };
  const positional: string[] = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i] as string;
    if (a === "--mode") {
      const v = argv[++i];
      if (v !== "strict" && v !== "lenient" && v !== "forensic") {
        throw new UsageError(
          `argument --mode: invalid choice: '${v ?? ""}' (choose from 'strict', 'lenient', 'forensic')`,
        );
      }
      args.mode = v;
    } else if (a === "--json") {
      args.json = true;
    } else if (a === "-o" || a === "--output") {
      const v = argv[++i];
      if (v === undefined) throw new UsageError(`argument ${a}: expected one argument`);
      args.output = v;
    } else if (a === "--strip-pii") {
      args.stripPii = true;
    } else if (a === "--include-raw") {
      args.includeRaw = true;
    } else if (a === "--no-unknown") {
      args.noUnknown = true;
    } else if (a.startsWith("-")) {
      throw new UsageError(`unrecognized arguments: ${a}`);
    } else {
      positional.push(a);
    }
  }
  if (positional.length === 0) throw new UsageError("the following arguments are required: file");
  if (positional.length > 1) {
    throw new UsageError(`unrecognized arguments: ${positional.slice(1).join(" ")}`);
  }
  args.file = positional[0] as string;
  return args;
}

function exitCode(result: ParseResult): number {
  if (result.errors.some((e) => e.code === "NOT_FIT_FORMAT" || e.code === "FIT_TOO_SMALL")) {
    return 4;
  }
  if (!result.ok) return 3;
  if (result.recovery !== null || result.errors.length > 0) return 2;
  return 0;
}

function summary(r: ParseResult, out: (line: string) => void): void {
  out(`file_type: ${r.fileType}   parts: ${r.parts.length}   mode: ${r.mode}`);
  const a = r.activity as { sessions: Session[]; device: unknown; gaps: unknown[] } | null;
  if (a !== null) {
    const dev = a.device as { manufacturer: unknown; product: unknown } | null;
    if (dev) out(`device: ${pyValue(dev.manufacturer)} product=${pyValue(dev.product)}`);
    a.sessions.forEach((s, i) => {
      const der = s.derived;
      const bits = [`records=${s.records.time.length}`];
      if (der.distanceM !== null) bits.push(`distance=${pyFixed(der.distanceM, 0)}m`);
      if (der.elapsedTimeS !== null) bits.push(`elapsed=${pyFixed(der.elapsedTimeS, 0)}s`);
      if (der.timerTimeS !== null) bits.push(`timer=${pyFixed(der.timerTimeS, 0)}s`);
      if (s.rebuilt) bits.push("REBUILT");
      if (s.discrepancies.length > 0) bits.push(`discrepancies=${s.discrepancies.length}`);
      out(`session[${i}] ${s.sport}: ${bits.join("  ")}`);
      for (const d of s.discrepancies.slice(0, 4)) {
        // the device's claim vs what its own records prove; platforms silently pick
        // different sides of this and users get four answers
        const delta = d.delta >= 0 ? `+${pyG(d.delta)}` : pyG(d.delta);
        out(
          `    ${d.field}: device says ${pyG(d.declared)}, records say ` +
            `${pyG(d.derived)} (delta ${delta})`,
        );
      }
      if (s.discrepancies.length > 4) {
        out(`    … and ${s.discrepancies.length - 4} more`);
      }
    });
    const gaps = a.gaps as { kind: string; durationS: number }[];
    if (gaps.length > 0) {
      const kinds = gaps
        .slice(0, 6)
        .map((g) => `${g.kind}(${pyFixed(g.durationS, 0)}s)`)
        .join(", ");
      out(`gaps: ${kinds}${gaps.length > 6 ? " …" : ""}`);
    }
  }
  if (r.recovery) {
    const rec = r.recovery;
    const est = rec.estimatedTotalRecords ? `/${rec.estimatedTotalRecords}(est)` : "";
    out(
      `recovery: ${rec.recoveredRecords}${est} messages,` +
        ` ${rec.bytesSkipped}B skipped, ${rec.resyncCount} resync(s)`,
    );
  }
  for (const p of r.provenance) out(`provenance: [${p.code}] ${p.detail}`);
  for (const w of r.warnings) out(`warning: [${w.code}] ${w.detail}`);
  for (const e of r.errors) {
    out(`error: [${e.code}] ${e.detail}${e.suggestion ? ` — ${e.suggestion}` : ""}`);
  }
}

/**
 * Python's `f"{v}"` for a value that may be None or a bool.
 *
 * `str(None)` is `"None"` and `String(null)` is `"null"`; likewise `True`/`true`.
 * The summary interpolates device fields straight into text, so this is visible
 * output rather than an internal detail.
 */
function pyValue(v: unknown): string {
  if (v === null || v === undefined) return "None";
  if (v === true) return "True";
  if (v === false) return "False";
  if (typeof v === "number" && !Number.isInteger(v)) return pyFloatStr(v);
  return String(v);
}

function pad(s: string, width: number): string {
  return s.padStart(width, " ");
}

function hex(v: number, width: number): string {
  return v.toString(16).toUpperCase().padStart(width, "0");
}

function cmdParse(argv: string[], out: (s: string) => void, err: (s: string) => void): number {
  let args: ParseArgs;
  try {
    args = parseArgs(argv);
  } catch (e) {
    if (e instanceof UsageError) {
      err(USAGE.trimEnd());
      err(`error: ${e.message}`);
      return 64;
    }
    throw e;
  }

  let data: Uint8Array;
  try {
    data = readFileBytes(args.file);
  } catch (e) {
    err(`cannot read ${args.file}: ${(e as Error).message}`);
    return 64;
  }

  let result: ParseResult;
  try {
    result = parse(data, {
      mode: args.mode,
      stripPii: args.stripPii,
      includeRaw: args.includeRaw,
      includeUnknown: !args.noUnknown,
    });
  } catch (e) {
    const fe = e as FitError;
    if (fe instanceof NotFitError) {
      err(`${fe.code}: ${fe.detail}`);
      return 4;
    }
    if (fe instanceof FitError) {
      err(`${fe.code}: ${fe.detail}`);
      if (fe.suggestion) err(`suggestion: ${fe.suggestion}`);
      return 3;
    }
    throw e;
  }

  if (args.json || args.output !== null) {
    const payload = result.toCanonicalJson();
    if (args.output !== null) writeFileBytes(args.output, payload);
    else out(new TextDecoder().decode(payload));
  } else {
    summary(result, out);
  }
  return exitCode(result);
}

function cmdInspect(argv: string[], out: (s: string) => void, err: (s: string) => void): number {
  let limit = 50;
  const positional: string[] = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i] as string;
    if (a === "--limit") {
      const v = argv[++i];
      const n = Number(v);
      if (v === undefined || !Number.isInteger(n)) {
        err(USAGE.trimEnd());
        err(`error: argument --limit: invalid int value: '${v ?? ""}'`);
        return 64;
      }
      limit = n;
    } else if (a.startsWith("-")) {
      err(USAGE.trimEnd());
      err(`error: unrecognized arguments: ${a}`);
      return 64;
    } else {
      positional.push(a);
    }
  }
  if (positional.length !== 1) {
    err(USAGE.trimEnd());
    err("error: the following arguments are required: file");
    return 64;
  }

  let data: Uint8Array;
  try {
    data = readFileBytes(positional[0] as string);
  } catch (e) {
    err(`cannot read ${positional[0]}: ${(e as Error).message}`);
    return 64;
  }

  let shown = 0;
  for (const ev of iterFrames(data)) {
    if (shown >= limit) {
      out("…");
      break;
    }
    if (ev.kind === "header") {
      out(
        `${pad(String(ev.offset), 8)}  header    size=${ev.size} proto=0x${hex(ev.protocolVersion, 2)}` +
          ` data_size=${ev.dataSize} crc_ok=${ev.crcOk === null ? "None" : ev.crcOk ? "True" : "False"}`,
      );
    } else if (ev.kind === "definition") {
      const dev = ev.devFields.length > 0 ? ` +${ev.devFields.length}dev` : "";
      const endian = ev.bigEndian ? "BE" : "LE";
      out(
        `${pad(String(ev.offset), 8)}  define    local=${ev.localId} global=${ev.globalNum}` +
          ` fields=${ev.fields.length}${dev} ${endian}`,
      );
    } else if (ev.kind === "data") {
      const comp = ev.timeOffset !== null ? ` toff=${ev.timeOffset}` : "";
      out(
        `${pad(String(ev.offset), 8)}  data      local=${ev.localId}` +
          ` global=${ev.definition.globalNum} bytes=${ev.payload.length}${comp}`,
      );
    } else if (ev.kind === "skipped") {
      out(`${pad(String(ev.offset), 8)}  SKIPPED   ${ev.length} bytes (${ev.reason})`);
    } else if (ev.kind === "crc") {
      out(
        `${pad(String(ev.offset), 8)}  crc       declared=0x${hex(ev.declared, 4)} ok=${ev.ok ? "True" : "False"}`,
      );
    } else {
      continue;
    }
    shown += 1;
  }
  return 0;
}

function cmdRepair(argv: string[], out: (s: string) => void, err: (s: string) => void): number {
  let mode: "lenient" | "forensic" = "lenient";
  let output: string | null = null;
  const positional: string[] = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i] as string;
    if (a === "--mode") {
      const v = argv[++i];
      if (v !== "lenient" && v !== "forensic") {
        err(USAGE.trimEnd());
        err(
          `error: argument --mode: invalid choice: '${v ?? ""}' (choose from 'lenient', 'forensic')`,
        );
        return 64;
      }
      mode = v;
    } else if (a === "-o" || a === "--output") {
      const v = argv[++i];
      if (v === undefined) {
        err(USAGE.trimEnd());
        err(`error: argument ${a}: expected one argument`);
        return 64;
      }
      output = v;
    } else if (a.startsWith("-")) {
      err(USAGE.trimEnd());
      err(`error: unrecognized arguments: ${a}`);
      return 64;
    } else {
      positional.push(a);
    }
  }
  if (positional.length !== 1 || output === null) {
    err(USAGE.trimEnd());
    err(
      `error: the following arguments are required: ${positional.length !== 1 ? "file" : "-o/--output"}`,
    );
    return 64;
  }

  let data: Uint8Array;
  try {
    data = readFileBytes(positional[0] as string);
  } catch (e) {
    err(`cannot read ${positional[0]}: ${(e as Error).message}`);
    return 64;
  }
  let rr: ReturnType<typeof repair>;
  try {
    rr = repair(data, { mode });
  } catch (e) {
    if (e instanceof NotRepairableError) {
      err(`${e.code}: ${e.detail}`);
      if (e.suggestion) err(`suggestion: ${e.suggestion}`);
      return 3;
    }
    if (e instanceof FitError) {
      err(`${e.code}: ${e.detail}`);
      return 3;
    }
    throw e;
  }
  writeFileBytes(output, rr.data);
  for (const pv of rr.provenance) out(`repair: [${pv.code}] ${pv.detail}`);
  if (rr.parseResult !== null && rr.parseResult.recovery !== null) {
    const rec = rr.parseResult.recovery;
    out(`salvage: ${rec.recoveredRecords} messages, ${rec.bytesSkipped}B skipped`);
  }
  out(
    `wrote ${output} (${rr.data.length} bytes); strict-valid: ${rr.outputStrictOk ? "True" : "False"}`,
  );
  return rr.outputStrictOk ? 0 : 2;
}

function cmdValidate(argv: string[], out: (s: string) => void, err: (s: string) => void): number {
  let platform: Platform = "strict-spec";
  const positional: string[] = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i] as string;
    if (a === "--platform") {
      const v = argv[++i];
      if (v !== "strict-spec" && v !== "garmin-connect" && v !== "strava") {
        err(USAGE.trimEnd());
        err(
          `error: argument --platform: invalid choice: '${v ?? ""}' (choose from 'strict-spec', 'garmin-connect', 'strava')`,
        );
        return 64;
      }
      platform = v;
    } else if (a.startsWith("-")) {
      err(USAGE.trimEnd());
      err(`error: unrecognized arguments: ${a}`);
      return 64;
    } else {
      positional.push(a);
    }
  }
  if (positional.length !== 1) {
    err(USAGE.trimEnd());
    err("error: the following arguments are required: file");
    return 64;
  }
  let data: Uint8Array;
  try {
    data = readFileBytes(positional[0] as string);
  } catch (e) {
    err(`cannot read ${positional[0]}: ${(e as Error).message}`);
    return 64;
  }
  const findings = validate(data, platform);
  for (const f of findings) out(`${f.level}: [${f.code}] ${f.detail}`);
  if (findings.some((f) => f.level === "error")) return 3;
  if (findings.length > 0) return 2;
  out(`valid for ${platform}`);
  return 0;
}

function parseBounds(
  raw: string | null,
  flag: string,
  err: (s: string) => void,
): number[] | null | false {
  if (raw === null) return null;
  const parts = raw.split(",").map((x) => Number(x));
  if (parts.some((x) => Number.isNaN(x))) {
    err(`error: ${flag} expects comma-separated numbers`);
    return false;
  }
  for (let i = 1; i < parts.length; i++) {
    if ((parts[i] as number) < (parts[i - 1] as number)) {
      err(`error: ${flag} bounds must ascend`);
      return false;
    }
  }
  return parts;
}

function cmdAnalyze(argv: string[], out: (s: string) => void, err: (s: string) => void): number {
  let mode: "strict" | "lenient" | "forensic" = "lenient";
  let json = false;
  let output: string | null = null;
  let ftp: number | null = null;
  let maxHr: number | null = null;
  let restingHr: number | null = null;
  let sex: string | null = null;
  let hrZones: string | null = null;
  let powerZones: string | null = null;
  const positional: string[] = [];
  const takeFloat = (flag: string, v: string | undefined): number | false => {
    const n = Number(v);
    if (v === undefined || Number.isNaN(n)) {
      err(USAGE.trimEnd());
      err(`error: argument ${flag}: invalid float value: '${v ?? ""}'`);
      return false;
    }
    return n;
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i] as string;
    if (a === "--mode") {
      const v = argv[++i];
      if (v !== "strict" && v !== "lenient" && v !== "forensic") {
        err(USAGE.trimEnd());
        err(
          `error: argument --mode: invalid choice: '${v ?? ""}' (choose from 'strict', 'lenient', 'forensic')`,
        );
        return 64;
      }
      mode = v;
    } else if (a === "--json") {
      json = true;
    } else if (a === "-o" || a === "--output") {
      const v = argv[++i];
      if (v === undefined) {
        err(USAGE.trimEnd());
        err(`error: argument ${a}: expected one argument`);
        return 64;
      }
      output = v;
    } else if (a === "--ftp") {
      const n = takeFloat(a, argv[++i]);
      if (n === false) return 64;
      ftp = n;
    } else if (a === "--max-hr") {
      const n = takeFloat(a, argv[++i]);
      if (n === false) return 64;
      maxHr = n;
    } else if (a === "--resting-hr") {
      const n = takeFloat(a, argv[++i]);
      if (n === false) return 64;
      restingHr = n;
    } else if (a === "--sex") {
      const v = argv[++i];
      if (v !== "male" && v !== "female") {
        err(USAGE.trimEnd());
        err(`error: argument --sex: invalid choice: '${v ?? ""}' (choose from 'male', 'female')`);
        return 64;
      }
      sex = v;
    } else if (a === "--hr-zones") {
      hrZones = argv[++i] ?? null;
    } else if (a === "--power-zones") {
      powerZones = argv[++i] ?? null;
    } else if (a.startsWith("-")) {
      err(USAGE.trimEnd());
      err(`error: unrecognized arguments: ${a}`);
      return 64;
    } else {
      positional.push(a);
    }
  }
  if (positional.length !== 1) {
    err(USAGE.trimEnd());
    err("error: the following arguments are required: file");
    return 64;
  }
  let data: Uint8Array;
  try {
    data = readFileBytes(positional[0] as string);
  } catch (e) {
    err(`cannot read ${positional[0]}: ${(e as Error).message}`);
    return 64;
  }
  let result: ParseResult;
  try {
    result = parse(data, { mode });
  } catch (e) {
    const fe = e as FitError;
    if (fe instanceof NotFitError) {
      err(`${fe.code}: ${fe.detail}`);
      return 4;
    }
    if (fe instanceof FitError) {
      err(`${fe.code}: ${fe.detail}`);
      return 3;
    }
    throw e;
  }
  const hb = parseBounds(hrZones, "--hr-zones", err);
  if (hb === false) return 64;
  const pb = parseBounds(powerZones, "--power-zones", err);
  if (pb === false) return 64;
  const settings: AthleteSettings = {
    ftpW: ftp,
    maxHr,
    restingHr,
    sex,
    hrZoneBounds: hb,
    powerZoneBounds: pb,
  };
  const report = analyze(result, settings);
  if (json || output !== null) {
    const payload = dumpsReportJson(reportToPlain(report));
    if (output !== null) writeFileBytes(output, new TextEncoder().encode(payload));
    else out(payload);
  } else {
    printReport(report.sessions, out);
  }
  return exitCode(result);
}

function printReport(sessions: WorkoutReport[], out: (s: string) => void): void {
  if (sessions.length === 0) {
    out("no activity sessions in this file (nothing to analyze)");
    return;
  }
  sessions.forEach((s, idx) => {
    const head = `session ${idx + 1}: ${s.sport}${s.subSport ? `/${s.subSport}` : ""}`;
    out(head);
    // Python `or`: a zero timer duration falls through to elapsed.
    const dur = s.durationS.get("timer") || s.durationS.get("elapsed");
    const bits: string[] = [];
    if (dur) {
      const total = Math.trunc(dur + 0.5);
      const m0 = Math.floor(total / 60);
      const sec = total - m0 * 60;
      const h = Math.floor(m0 / 60);
      const m = m0 - h * 60;
      bits.push(
        h
          ? `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`
          : `${m}:${String(sec).padStart(2, "0")}`,
      );
    }
    if (s.distanceM) bits.push(`${pyFixed(s.distanceM / 1000, 2)} km`);
    if (s.pace) {
      bits.push(`${String(s.pace.formatted)} (${String(s.pace.basis)})`);
    } else if (s.avgSpeedKmh) {
      const basis = s.avgSpeedBasis !== "timer" ? ` (${s.avgSpeedBasis})` : "";
      bits.push(`${pyFixed(s.avgSpeedKmh, 1)} km/h${basis}`);
    }
    if (s.avgPrimary !== null && s.primarySignal === "power") {
      bits.push(`avg ${pyFixed(s.avgPrimary, 0)} W`);
      if (s.weightedAvgPower) bits.push(`weighted ${pyFixed(s.weightedAvgPower, 0)} W`);
    }
    if (s.avgHr !== null) bits.push(`avg HR ${pyFixed(s.avgHr, 0)}`);
    if (bits.length > 0) out(`  ${bits.join(" · ")}`);
    if (s.structure !== null && s.structure.basis !== "none") {
      const labels = s.structure.repeats.map((g) => g.label).join("; ") || "intervals";
      out(`  structure [${s.structure.basis}]: ${labels}`);
    }
    if (s.load !== null) out(`  load ${pyFixed(s.load.value, 0)} [${s.load.basis}]`);
    for (const ins of s.insights) out(`  ${ins.code}: ${ins.message}`);
    for (const o of s.omissions) out(`  (omitted) ${o}`);
  });
}

function cmdCodes(out: (s: string) => void): number {
  const tables: [string, Readonly<Record<string, string>>][] = [
    ["errors", ERROR_CODES],
    ["warnings", WARNING_CODES],
    ["provenance", PROVENANCE_CODES],
  ];
  for (const [title, table] of tables) {
    out(`# ${title}`);
    for (const [code, desc] of Object.entries(table)) out(`${code}\t${desc}`);
  }
  return 0;
}

/** Accept plain seconds or ±HH:MM (the form humans think in for timezones). */
function parseTimeShift(raw: string | null, err: (s: string) => void): number | null | false {
  if (raw === null) return null;
  let text = raw.trim();
  const sign = text.startsWith("-") ? -1 : 1;
  text = text.replace(/^[+-]+/, "");
  const asInt = (s: string): number | null => (/^\d+$/.test(s) ? Number(s) : null);
  if (text.includes(":")) {
    const at = text.indexOf(":");
    const hours = asInt(text.slice(0, at));
    const minutes = asInt(text.slice(at + 1));
    if (hours === null || minutes === null) {
      err(`error: --time-shift expects seconds or ±HH:MM, got ${JSON.stringify(raw)}`);
      return false;
    }
    return sign * (hours * 3600 + minutes * 60);
  }
  const secs = asInt(text);
  if (secs === null) {
    err(`error: --time-shift expects seconds or ±HH:MM, got ${JSON.stringify(raw)}`);
    return false;
  }
  return sign * secs;
}

function cmdEdit(argv: string[], out: (s: string) => void, err: (s: string) => void): number {
  let mode: Mode = "lenient";
  let output: string | null = null;
  let sport: string | null = null;
  let subSport: string | null = null;
  let manufacturer: string | null = null;
  let product: number | null = null;
  let totalDistance: number | null = null;
  let timeShiftRaw: string | null = null;
  const positional: string[] = [];
  const takeStr = (flag: string): string | false => {
    const v = argv[++i];
    if (v === undefined) {
      err(USAGE.trimEnd());
      err(`error: argument ${flag}: expected one argument`);
      return false;
    }
    return v;
  };
  let i = 0;
  for (; i < argv.length; i++) {
    const a = argv[i] as string;
    if (a === "--mode") {
      const v = argv[++i];
      if (v !== "strict" && v !== "lenient" && v !== "forensic") {
        err(USAGE.trimEnd());
        err(
          `error: argument --mode: invalid choice: '${v ?? ""}' (choose from 'strict', 'lenient', 'forensic')`,
        );
        return 64;
      }
      mode = v;
    } else if (a === "-o" || a === "--output") {
      const v = takeStr(a);
      if (v === false) return 64;
      output = v;
    } else if (a === "--sport") {
      const v = takeStr(a);
      if (v === false) return 64;
      sport = v;
    } else if (a === "--sub-sport") {
      const v = takeStr(a);
      if (v === false) return 64;
      subSport = v;
    } else if (a === "--manufacturer") {
      const v = takeStr(a);
      if (v === false) return 64;
      manufacturer = v;
    } else if (a === "--product") {
      const v = takeStr(a);
      if (v === false) return 64;
      const n = Number(v);
      if (!/^[+-]?\d+$/.test(v.trim()) || !Number.isSafeInteger(n)) {
        err(USAGE.trimEnd());
        err(`error: argument --product: invalid int value: '${v}'`);
        return 64;
      }
      product = n;
    } else if (a === "--total-distance") {
      const v = takeStr(a);
      if (v === false) return 64;
      const n = Number(v);
      if (v.trim() === "" || Number.isNaN(n)) {
        err(USAGE.trimEnd());
        err(`error: argument --total-distance: invalid float value: '${v}'`);
        return 64;
      }
      totalDistance = n;
    } else if (a === "--time-shift") {
      const v = takeStr(a);
      if (v === false) return 64;
      timeShiftRaw = v;
    } else if (a.startsWith("-")) {
      err(USAGE.trimEnd());
      err(`error: unrecognized arguments: ${a}`);
      return 64;
    } else {
      positional.push(a);
    }
  }
  if (positional.length !== 1 || output === null) {
    err(USAGE.trimEnd());
    err(
      `error: the following arguments are required: ${positional.length !== 1 ? "file" : "-o/--output"}`,
    );
    return 64;
  }

  const shift = parseTimeShift(timeShiftRaw, err);
  if (shift === false) return 64;
  // Python truthiness: a parsed shift of 0 does not count as a requested change.
  if (
    !sport &&
    !subSport &&
    !manufacturer &&
    product === null &&
    !shift &&
    totalDistance === null
  ) {
    err("error: edit requires at least one change");
    err(
      "suggestion: --sport / --sub-sport / --manufacturer / --product /" +
        " --time-shift / --total-distance",
    );
    return 64;
  }

  let data: Uint8Array;
  try {
    data = readFileBytes(positional[0] as string);
  } catch (e) {
    err(`cannot read ${positional[0]}: ${(e as Error).message}`);
    return 64;
  }
  let result: ReturnType<typeof edit>;
  try {
    result = edit(data, {
      sport,
      subSport,
      manufacturer,
      product,
      timeShiftS: shift,
      totalDistanceM: totalDistance,
      mode,
    });
  } catch (e) {
    if (e instanceof NotFitError) {
      err(`${e.code}: ${e.detail}`);
      return 4;
    }
    if (e instanceof FitError) {
      err(`${e.code}: ${e.detail}`);
      if (e.suggestion) err(`suggestion: ${e.suggestion}`);
      return 3;
    }
    throw e;
  }

  writeFileBytes(output, result.data);
  for (const entry of result.provenance) out(`${entry.code}: ${entry.detail}`);
  for (const warn of result.warnings) err(`${warn.code}: ${warn.detail}`);
  out(`wrote ${output} (${result.data.length} bytes)`);
  if (!result.outputStrictOk) {
    err("warning: the edited file does not parse in strict mode; inspect before uploading");
    return 2;
  }
  return 0;
}

/**
 * Run the CLI. `out` and `err` are injected so the parity harness can capture
 * output without spawning a process per case.
 */
export function main(
  argv: string[],
  out: (s: string) => void = (s) => console.log(s),
  err: (s: string) => void = (s) => console.error(s),
): number {
  const command = argv[0];
  const rest = argv.slice(1);
  if (command === undefined || command === "-h" || command === "--help") {
    if (command === undefined) {
      err(USAGE.trimEnd());
      err("error: the following arguments are required: command");
      return 64;
    }
    out(USAGE.trimEnd());
    return 0;
  }
  if (command === "parse") return cmdParse(rest, out, err);
  if (command === "inspect") return cmdInspect(rest, out, err);
  if (command === "repair") return cmdRepair(rest, out, err);
  if (command === "validate") return cmdValidate(rest, out, err);
  if (command === "edit") return cmdEdit(rest, out, err);
  if (command === "analyze") return cmdAnalyze(rest, out, err);
  if (command === "codes") return cmdCodes(out);
  err(USAGE.trimEnd());
  err(
    `error: argument command: invalid choice: '${command}' (choose from 'parse', 'inspect', 'repair', 'validate', 'edit', 'analyze', 'codes')`,
  );
  return 64;
}
