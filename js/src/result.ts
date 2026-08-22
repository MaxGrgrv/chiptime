/**
 * ParseResult and canonical output shaping (schema `chiptime/1`, ADR-0002).
 *
 * Twin of `python/src/chiptime/result.py`.
 */

import { MAX_SAFE_INT, dumps } from "./canonical.js";
import { fitTsToIso } from "./decode.js";
import type { Diagnostic, FitError, ProvenanceEntry } from "./errors.js";
import type { FieldValue, Message } from "./message.js";
import type { Activity, Session, Totals } from "./model.js";

export type Mode = "strict" | "lenient" | "forensic";

export const SCHEMA_VERSION = 1;

/**
 * Identity of the parsed input.
 *
 * `path` is kept for humans but **never serialized** — privacy and determinism,
 * ADR-0002 §3. `sha256` is the stable identity; cache and dedupe on it.
 */
export interface SourceInfo {
  readonly path: string | null;
  readonly sizeBytes: number;
  readonly sha256: string;
  readonly unwrapped: readonly string[];
}

/** What salvage did, when it had to. Absent means the file needed none. */
export interface RecoveryReport {
  readonly recoveredRecords: number;
  readonly estimatedTotalRecords: number | null;
  readonly bytesRead: number;
  readonly bytesSkipped: number;
  readonly resyncCount: number;
}

/** One FIT file within the source. Chained files yield several parts. */
export interface FitPart {
  fileType: string;
  fileId: Map<string, unknown> | null;
  messages: Message[];
  /** The semantic model for activity parts; populated at F36. */
  activity: unknown;
}

/** Bytes to hex; magnitudes beyond 2^53−1 to decimal strings (ADR-0002 §2). */
export function jsonSafe(v: unknown): unknown {
  if (v instanceof Uint8Array) {
    let out = "";
    for (const b of v) out += b.toString(16).padStart(2, "0");
    return out;
  }
  if (v === null || typeof v === "boolean") return v;
  if (typeof v === "bigint") {
    return v > BigInt(MAX_SAFE_INT) || v < BigInt(-MAX_SAFE_INT) ? v.toString() : Number(v);
  }
  if (typeof v === "number" && Number.isInteger(v) && Math.abs(v) > MAX_SAFE_INT) {
    return String(v);
  }
  if (Array.isArray(v)) return v.map(jsonSafe);
  return v;
}

export interface ParseResultInit {
  ok: boolean;
  mode: Mode;
  source: SourceInfo;
  parts: FitPart[];
  provenance: ProvenanceEntry[];
  warnings: Diagnostic[];
  errors: FitError[];
  recovery: RecoveryReport | null;
  includeRaw?: boolean;
}

/** Everything `parse` learned about one source. */
export class ParseResult {
  readonly ok: boolean;
  readonly mode: Mode;
  readonly source: SourceInfo;
  readonly parts: FitPart[];
  readonly provenance: ProvenanceEntry[];
  readonly warnings: Diagnostic[];
  readonly errors: FitError[];
  readonly recovery: RecoveryReport | null;
  private readonly includeRaw: boolean;

  constructor(init: ParseResultInit) {
    this.ok = init.ok;
    this.mode = init.mode;
    this.source = init.source;
    this.parts = init.parts;
    this.provenance = init.provenance;
    this.warnings = init.warnings;
    this.errors = init.errors;
    this.recovery = init.recovery;
    this.includeRaw = init.includeRaw ?? false;
  }

  private primary(): FitPart | undefined {
    return this.parts.find((p) => p.fileType === "activity") ?? this.parts[0];
  }

  get fileType(): string {
    return this.primary()?.fileType ?? "unknown";
  }

  get messages(): Message[] {
    return this.primary()?.messages ?? [];
  }

  get activity(): unknown {
    return this.primary()?.activity ?? null;
  }

  toJSON(): unknown {
    return {
      chiptime_schema: SCHEMA_VERSION,
      ok: this.ok,
      mode: this.mode,
      source: {
        sha256: this.source.sha256,
        size_bytes: this.source.sizeBytes,
        unwrapped: [...this.source.unwrapped],
      },
      parts: this.parts.map((p) => this.partJson(p)),
      errors: this.errors.map((e) => ({
        code: e.code,
        detail: e.detail,
        byte_offset: e.byteOffset,
        suggestion: e.suggestion,
      })),
      warnings: this.warnings.map((w) => ({ code: w.code, detail: w.detail, scope: w.scope })),
      provenance: this.provenance.map((p) => ({
        code: p.code,
        action: p.action,
        scope: p.scope,
        detail: p.detail,
        byte_offset: p.byteOffset,
        // Python sorts the data keys before serializing; canonical JSON sorts them
        // again, so this only matters for readers of `toJSON()`.
        data: Object.fromEntries(
          Object.entries(p.data)
            .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
            .map(([k, v]) => [k, jsonSafe(v)]),
        ),
      })),
      recovery:
        this.recovery === null
          ? null
          : {
              recovered_records: this.recovery.recoveredRecords,
              estimated_total_records: this.recovery.estimatedTotalRecords,
              bytes_read: this.recovery.bytesRead,
              bytes_skipped: this.recovery.bytesSkipped,
              resync_count: this.recovery.resyncCount,
            },
    };
  }

  toCanonicalJson(): Uint8Array {
    return dumps(this.toJSON());
  }

  private partJson(part: FitPart): unknown {
    // With a semantic model, record messages live losslessly in streams -- every
    // field (native, unknown, developer) becomes a stream column, so they are not
    // repeated here.
    const msgs =
      part.activity !== null && part.activity !== undefined
        ? part.messages.filter((m) => m.globalNum !== 20)
        : part.messages;
    return {
      file_type: part.fileType,
      file_id:
        part.fileId === null
          ? null
          : Object.fromEntries([...part.fileId].map(([k, v]) => [k, jsonSafe(v)])),
      activity:
        part.activity === null || part.activity === undefined
          ? null
          : activityJson(part.activity as Activity),
      messages: msgs.map((m) => this.messageJson(m)),
    };
  }

  private messageJson(m: Message): unknown {
    const fields: Record<string, unknown> = {};
    for (const [fname, fv] of m.fields) {
      fields[fname] = this.fieldJson(fv);
    }
    return {
      name: m.name,
      global_num: m.globalNum,
      offset: m.byteOffset,
      fields,
    };
  }

  private fieldJson(fv: FieldValue): unknown {
    const entry: Record<string, unknown> = { value: jsonSafe(fv.value) };
    if (fv.units !== null) entry.units = fv.units;
    if (this.includeRaw) entry.raw = jsonSafe(fv.raw);
    if (fv.developer !== null) {
      entry.developer = {
        developer_data_index: fv.developer.developerDataIndex,
        field_definition_number: fv.developer.fieldDefinitionNumber,
        application_id: fv.developer.applicationId,
        vendor: fv.developer.vendor,
        canonical_name: fv.developer.canonicalName,
      };
    }
    return entry;
  }
}

/**
 * `_iso(dt)` in Python: `strftime("%Y-%m-%dT%H:%M:%SZ")`, never `toISOString()`.
 *
 * Floors first. A model time can be fractional — `end = start + total_elapsed_time`
 * where elapsed is a float — and Python holds that as a `datetime` carrying
 * microseconds, which `strftime` then drops. The integer formatter needs whole
 * seconds, so the truncation happens here rather than being smeared into the
 * civil-date arithmetic.
 */
function iso(t: number | null): string | null {
  return t === null ? null : fitTsToIso(Math.floor(t));
}

function totalsJson(t: Totals): unknown {
  return {
    elapsed_time_s: t.elapsedTimeS,
    timer_time_s: t.timerTimeS,
    moving_time_s: t.movingTimeS,
    distance_m: t.distanceM,
    ascent_m: t.ascentM,
    descent_m: t.descentM,
    calories_kcal: t.caloriesKcal,
    avg: sortedMap(t.avg),
    max: sortedMap(t.max),
  };
}

function sortedMap(m: Map<string, number>): Record<string, number> {
  return Object.fromEntries([...m.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)));
}

function sessionJson(s: Session): unknown {
  return {
    sport: s.sport,
    sub_sport: s.subSport,
    start_time: iso(s.startTime),
    end_time: iso(s.endTime),
    rebuilt: s.rebuilt,
    declared: s.declared === null ? null : totalsJson(s.declared),
    derived: totalsJson(s.derived),
    discrepancies: s.discrepancies.map((d) => ({
      field: d.field,
      declared: d.declared,
      derived: d.derived,
      delta: d.delta,
    })),
    laps: s.laps.map((lap) => ({
      message_index: lap.messageIndex,
      start_time: iso(lap.startTime),
      end_time: iso(lap.endTime),
      sport: lap.sport,
      declared: lap.declared === null ? null : totalsJson(lap.declared),
    })),
    lengths: s.lengths.map((ln) => ({
      start_time: iso(ln.startTime),
      end_time: iso(ln.endTime),
      length_type: ln.lengthType,
      swim_stroke: ln.swimStroke,
      total_strokes: ln.totalStrokes,
      total_elapsed_time_s: ln.totalElapsedTimeS,
    })),
    records: {
      n: s.records.time.length,
      time: s.records.time.map(iso),
      streams: Object.fromEntries(
        [...s.records.streams.entries()]
          .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
          .map(([name, st]) => [
            name,
            { units: st.units, source: st.source, values: st.values.map(jsonSafe) },
          ]),
      ),
    },
  };
}

function activityJson(a: Activity): unknown {
  return {
    local_timestamp: a.localTimestamp,
    utc_offset_s: a.utcOffsetS,
    hrv_intervals_s: [...a.hrvIntervalsS],
    device:
      a.device === null
        ? null
        : {
            manufacturer: a.device.manufacturer,
            product: a.device.product,
            product_name: a.device.productName,
            serial_number: a.device.serialNumber,
            software_version: a.device.softwareVersion,
          },
    athlete:
      a.athlete === null
        ? null
        : {
            friendly_name: a.athlete.friendlyName,
            gender: a.athlete.gender,
            age: a.athlete.age,
            weight_kg: a.athlete.weightKg,
            height_m: a.athlete.heightM,
          },
    events: a.events.map((e) => ({
      time: iso(e.time),
      event: e.event,
      event_type: e.eventType,
      data: e.data,
    })),
    gaps: a.gaps.map((g) => ({
      start: iso(g.start),
      end: iso(g.end),
      duration_s: g.durationS,
      kind: g.kind,
      evidence: g.evidence,
    })),
    sessions: a.sessions.map(sessionJson),
  };
}
