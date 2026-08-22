/**
 * The canonical semantic model (PRD section 7): Activity -> Sessions -> Laps/Records.
 *
 * Twin of `python/src/chiptime/model.py`, with one deliberate structural
 * difference: **times are FIT seconds, not `Date`.** Every timestamp in the
 * canonical activity block goes through `strftime("%Y-%m-%dT%H:%M:%SZ")` in Python,
 * so the integer formatter reproduces it exactly, and `Date` — banned in `js/src`
 * since F34 — is never needed (ADR-0009 section 5).
 *
 * Structural invariants:
 * - `Stream.values`: `null` means ABSENT (sentinel or dropout); `0` is a real zero
 *   (taxonomy #64). Streams are independently sparse (#68).
 * - Lap/Session end times derive from `startTime + totalElapsedTime`, never from the
 *   summary message's write-timestamp (taxonomy #50).
 */

/** FIT seconds since 1989-12-31T00:00:00Z. `null` where a record carried no time. */
export type FitTime = number | null;

/**
 * One column of record data — every FIT record field becomes a stream.
 *
 * The honesty rule lives here: in `values`, `null` means the sensor said *nothing*
 * (dropout, sentinel on the wire) and `0` means it said *zero* (coasting). They are
 * never conflated, so a wire sentinel can never leak into an average.
 */
export interface Stream {
  readonly name: string;
  readonly units: string | null;
  /** One entry per record, index-aligned with `Records.time`. */
  readonly values: unknown[];
  /** `native` | `developer:<vendor>` | `developer` */
  readonly source: string;
}

export function presentCount(s: Stream): number {
  let n = 0;
  for (const v of s.values) if (v !== null && v !== undefined) n++;
  return n;
}

/**
 * The per-second timeline, stored as columns rather than rows.
 *
 * One shared `time` axis plus one `Stream` per field that ever appeared in a record
 * — lossless (unknown fields become streams too) and analytics-friendly.
 * Row-oriented access is a view, not the storage.
 *
 * `to_pandas` has no TypeScript analogue and is deliberately absent.
 */
export interface Records {
  time: FitTime[];
  /** Insertion order is wire order; canonical output sorts by name. */
  streams: Map<string, Stream>;
}

export function emptyRecords(): Records {
  return { time: [], streams: new Map() };
}

export function recordCount(r: Records): number {
  return r.time.length;
}

export function getStream(r: Records, name: string): Stream | undefined {
  return r.streams.get(name);
}

export function* rows(r: Records): Generator<Record<string, unknown>> {
  for (let i = 0; i < r.time.length; i++) {
    const row: Record<string, unknown> = { time: r.time[i] };
    for (const [name, s] of r.streams) row[name] = s.values[i];
    yield row;
  }
}

/**
 * One set of summary numbers for a session or lap.
 *
 * Appears twice on a `Session` — `declared` (the device's claim, absent if the
 * message never arrived) and `derived` (recomputed from the records). Keeping both
 * is the point: devices lie, and the disagreement is signal.
 */
export interface Totals {
  elapsedTimeS: number | null;
  timerTimeS: number | null;
  movingTimeS: number | null;
  distanceM: number | null;
  ascentM: number | null;
  descentM: number | null;
  caloriesKcal: number | null;
  avg: Map<string, number>;
  max: Map<string, number>;
}

export function emptyTotals(): Totals {
  return {
    elapsedTimeS: null,
    timerTimeS: null,
    movingTimeS: null,
    distanceM: null,
    ascentM: null,
    descentM: null,
    caloriesKcal: null,
    avg: new Map(),
    max: new Map(),
  };
}

/**
 * One declared lap. `endTime` is always start + elapsed — never the message's write
 * timestamp, which devices emit late (taxonomy #50).
 */
export interface Lap {
  messageIndex: number | null;
  startTime: FitTime;
  endTime: FitTime;
  declared: Totals | null;
  sport: string | null;
}

/**
 * One pool length — the atom of swim structure. `lengthType` is `active` for swum
 * lengths and `idle` for wall rest; zero-length wall artifacts are flagged during
 * reconciliation, not silently dropped.
 */
export interface Length {
  startTime: FitTime;
  endTime: FitTime;
  lengthType: string | null;
  swimStroke: string | null;
  totalStrokes: number | null;
  totalElapsedTimeS: number | null;
}

/**
 * A hole in the recording, classified with evidence — an auto-pause is not
 * corruption, and `kind` says which is which.
 */
export interface Gap {
  start: number;
  end: number;
  durationS: number;
  /** `smart_recording | auto_pause | manual_stop | post_timer | corruption | unknown` */
  kind: string;
  evidence: string;
}

/**
 * A disagreement between what the device declared and what the records prove —
 * surfaced, never silently reconciled.
 */
export interface Discrepancy {
  field: string;
  declared: number;
  derived: number;
  /** `derived - declared` */
  delta: number;
}

/**
 * One continuous bout of one sport — the center of the model.
 *
 * A workout has one session per sport segment (a triathlon has five: swim,
 * transition, bike, transition, run).
 */
export interface Session {
  sport: string;
  subSport: string | null;
  startTime: FitTime;
  /** Start + declared elapsed when known. */
  endTime: FitTime;
  laps: Lap[];
  lengths: Length[];
  records: Records;
  declared: Totals | null;
  derived: Totals;
  discrepancies: Discrepancy[];
  /** True when synthesized from records because no session message survived (#95). */
  rebuilt: boolean;
}

export function newSession(sport: string, subSport: string | null): Session {
  return {
    sport,
    subSport,
    startTime: null,
    endTime: null,
    laps: [],
    lengths: [],
    records: emptyRecords(),
    declared: null,
    derived: emptyTotals(),
    discrepancies: [],
    rebuilt: false,
  };
}

/** What recorded the file. Vendor quirk handling keys off this. */
export interface DeviceInfo {
  manufacturer: string | number | null;
  product: number | null;
  productName: string | null;
  serialNumber: number | null;
  softwareVersion: number | null;
}

export interface AthleteProfile {
  friendlyName: string | null;
  gender: string | null;
  age: number | null;
  weightKg: number | null;
  heightM: number | null;
}

export interface Event {
  time: FitTime;
  event: string | number | null;
  eventType: string | number | null;
  data: number | null;
}

/** The whole workout: every session plus file-level context. */
export interface Activity {
  sessions: Session[];
  events: Event[];
  gaps: Gap[];
  device: DeviceInfo | null;
  athlete: AthleteProfile | null;
  /** Raw local-time string from the activity message. */
  localTimestamp: string | null;
  /** Validated local-UTC offset (ADR-0005 §4), or null. */
  utcOffsetS: number | null;
  /** Beat-to-beat RR intervals when the file logged HRV (#72). */
  hrvIntervalsS: number[];
}

export function emptyActivity(): Activity {
  return {
    sessions: [],
    events: [],
    gaps: [],
    device: null,
    athlete: null,
    localTimestamp: null,
    utcOffsetS: null,
    hrvIntervalsS: [],
  };
}
