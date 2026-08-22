/**
 * Gap classification (taxonomy #43/#44) per ADR-0005 §7. Never interpolates.
 *
 * Twin of `python/src/chiptime/semantics/gaps.py`.
 */

import { fitTsToIso } from "../decode.js";
import type { Event, Gap } from "../model.js";
import { pyRound } from "../numeric.js";
import { type TimerState, finalStop as stateFinalStop } from "./timers.js";

export const GAP_MIN_S = 10.0; // below this: not worth reporting
export const SMART_RECORDING_MAX_S = 30.0;

/** Python's `t.strftime('%H:%M:%S')`, taken from the integer formatter. */
function hms(fitSeconds: number): string {
  return fitTsToIso(fitSeconds).slice(11, 19);
}

/**
 * Python's `f"{dt:.0f}"`, which rounds **half to even** — `f"{2.5:.0f}"` is `"2"`.
 * `toFixed(0)` rounds half away from zero and would print `"3"`.
 */
function fmt0(x: number): string {
  return String(pyRound(x));
}

export function classifyGaps(
  times: (number | null)[],
  offsets: number[],
  state: TimerState,
  events: Event[],
  skippedRanges: [number, number][],
): Gap[] {
  const stops = events.filter(
    (e) =>
      e.event === "timer" &&
      (e.eventType === "stop" || e.eventType === "stop_all") &&
      e.time !== null,
  );
  const final = stateFinalStop(state);
  const gaps: Gap[] = [];
  for (let i = 0; i < times.length - 1; i++) {
    const t0 = times[i];
    const t1 = times[i + 1];
    if (t0 === null || t0 === undefined || t1 === null || t1 === undefined) continue;
    const dt = t1 - t0;
    if (dt < GAP_MIN_S) continue;
    gaps.push(
      classify(
        t0,
        t1,
        dt,
        offsets[i] as number,
        offsets[i + 1] as number,
        stops,
        final,
        skippedRanges,
      ),
    );
  }
  return gaps;
}

function classify(
  t0: number,
  t1: number,
  dt: number,
  off0: number,
  off1: number,
  stops: Event[],
  final: number | null,
  skippedRanges: [number, number][],
): Gap {
  // corruption: the two records straddle a resynchronized byte range
  for (const [a, b] of skippedRanges) {
    if (off0 < a && off1 > b) {
      return {
        start: t0,
        end: t1,
        durationS: dt,
        kind: "corruption",
        evidence: `${b - a} corrupt byte(s) were skipped between these records`,
      };
    }
  }

  // a stop event inside the gap -> deliberate pause/stop
  for (const e of stops) {
    const et = e.time as number;
    if (t0 <= et && et <= t1) {
      const trigger = e.data === 1 ? "auto" : "manual";
      const kind = trigger === "auto" ? "auto_pause" : "manual_stop";
      return {
        start: t0,
        end: t1,
        durationS: dt,
        kind,
        evidence: `timer ${String(e.eventType)} (${trigger}) at ${hms(et)} inside the gap`,
      };
    }
  }

  if (final !== null && t0 >= final) {
    return {
      start: t0,
      end: t1,
      durationS: dt,
      kind: "post_timer",
      evidence: "records written after the final timer stop (excluded from stats)",
    };
  }

  if (dt <= SMART_RECORDING_MAX_S) {
    return {
      start: t0,
      end: t1,
      durationS: dt,
      kind: "smart_recording",
      evidence: "short event-less gap; smart recording writes only on change",
    };
  }

  return {
    start: t0,
    end: t1,
    durationS: dt,
    kind: "unknown",
    evidence: `no timer events explain this ${fmt0(dt)}s silence`,
  };
}
