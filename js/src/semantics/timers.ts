/**
 * Timer state machine (taxonomy #45) and the three durations (#46).
 *
 * Twin of `python/src/chiptime/semantics/timers.py`. Defensive by design:
 * unbalanced events are tolerated and recorded, never fatal. Policies per
 * ADR-0005 sections 5-6.
 *
 * Times are FIT seconds throughout, so a duration is plain subtraction rather than
 * a `timedelta` (see `model.ts` for why `Date` never appears).
 */

import type { Diagnostic, ProvenanceEntry } from "../errors.js";
import type { Event } from "../model.js";

export const MOVING_SPEED_FLOOR = 0.1; // m/s: below this a rider/runner is stationary
export const MOVING_DT_CAP = 30.0; // s: one record never contributes more than this

export interface TimerState {
  intervals: [number, number][];
  synthesizedFinalStop: boolean;
  stopWithoutStart: boolean;
}

export function runningAt(state: TimerState, t: number): boolean {
  return state.intervals.some(([a, b]) => a <= t && t <= b);
}

export function finalStop(state: TimerState): number | null {
  const last = state.intervals[state.intervals.length - 1];
  return last ? last[1] : null;
}

export function timerSeconds(state: TimerState): number | null {
  if (state.intervals.length === 0) return null;
  let total = 0;
  for (const [a, b] of state.intervals) total += b - a;
  return total;
}

const STOP_KINDS = new Set(["stop", "stop_all", "stop_disable_all"]);

export function buildTimerState(
  events: Event[],
  firstRecord: number | null,
  lastRecord: number | null,
  warnings: Diagnostic[],
  provenance: ProvenanceEntry[],
  scope: string,
): TimerState {
  const startsStops: [number, string][] = [];
  for (const e of events) {
    if (
      e.event === "timer" &&
      e.time !== null &&
      typeof e.eventType === "string" &&
      (e.eventType === "start" || STOP_KINDS.has(e.eventType))
    ) {
      startsStops.push([e.time, e.eventType]);
    }
  }

  let intervals: [number, number][] = [];
  let openStart: number | null = null;
  let stopWithoutStart = false;
  for (const [t, kind] of startsStops) {
    if (kind === "start") {
      // start-while-running: ignore (consecutive starts seen in the wild)
      if (openStart === null) openStart = t;
    } else {
      if (openStart === null) {
        const anchor = firstRecord ?? t;
        if (intervals.length > 0 || anchor >= t) {
          // Redundant stop (#45): shutdown patterns write stop_all after the final
          // stop (Wahoo), and multisport slicing leaks the previous session's
          // boundary stop into the next window (Suunto). Nothing is open to close:
          // ignored.
          provenance.push({
            code: "TIMER_REDUNDANT_STOP",
            action: "ignored",
            scope,
            detail: "timer stop event with no interval open ignored as redundant",
            byteOffset: null,
            data: {},
          });
          continue;
        }
        // Stop without start (#45): interval opened at the first record.
        stopWithoutStart = true;
        openStart = anchor;
        warnings.push({
          code: "TIMER_STOP_WITHOUT_START",
          detail: "timer stop event with no preceding start; interval opened at the first record",
          scope,
        });
      }
      if (openStart <= t) intervals.push([openStart, t]);
      openStart = null;
    }
  }

  let synthesized = false;
  if (openStart !== null) {
    // Missing final stop (crash class, #45): close at the last record.
    const end = lastRecord ?? openStart;
    if (openStart < end) {
      intervals.push([openStart, end]);
      synthesized = true;
      provenance.push({
        code: "TIMER_STOP_SYNTHESIZED",
        action: "synthesized",
        scope,
        detail: "no final timer stop event; timer closed at the last record",
        byteOffset: null,
        data: {},
      });
    } else {
      // Start at or after the last record (#45): the mirror of the redundant
      // stop — multisport slicing leaks the next session's boundary start into
      // this window. No timer time evidence: ignored.
      provenance.push({
        code: "TIMER_REDUNDANT_START",
        action: "ignored",
        scope,
        detail: "timer start event with no timer time after it ignored as redundant",
        byteOffset: null,
        data: {},
      });
    }
  }
  if (startsStops.length === 0 && firstRecord !== null && lastRecord !== null) {
    // No timer events at all (minimal encoders, #88 class): the record span is the
    // best available timer estimate; recorded as-is, not as synthesized events.
    intervals = [[firstRecord, lastRecord]];
  }

  return { intervals, synthesizedFinalStop: synthesized, stopWithoutStart };
}

/** ADR-0005 §6: speed-gated moving time; `null` without a speed stream. */
export function movingSeconds(
  times: (number | null)[],
  speeds: unknown[] | null,
  state: TimerState,
): number | null {
  if (speeds === null) return null;
  let total = 0;
  for (let i = 0; i < times.length - 1; i++) {
    const t0 = times[i];
    const t1 = times[i + 1];
    if (t0 === null || t0 === undefined || t1 === null || t1 === undefined) continue;
    const v = speeds[i];
    if (typeof v !== "number" || v <= MOVING_SPEED_FLOOR) continue;
    if (!runningAt(state, t0)) continue;
    const dt = t1 - t0;
    if (dt > 0) total += Math.min(dt, MOVING_DT_CAP);
  }
  return total;
}
