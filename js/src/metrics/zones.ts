/**
 * Zone resolution ladder (ADR-0008 §4): explicit settings > in-file zone messages >
 * absent. Never estimated from the workout itself.
 *
 * Twin of `python/src/chiptime/metrics/zones.py`.
 */

import type { Message } from "../message.js";
import type { AthleteSettings } from "./settings.js";

function boundsFromMessages(
  messages: readonly Message[] | null,
  msgName: string,
  field: string,
): number[] | null {
  if (!messages || messages.length === 0) return null;
  const indexed: [number, number][] = [];
  for (const m of messages) {
    if (m.name !== msgName) continue;
    const v = m.fields.get(field)?.value;
    if (typeof v === "number") {
      const idx = m.fields.get("message_index")?.value;
      indexed.push([typeof idx === "number" && Number.isInteger(idx) ? idx : indexed.length, v]);
    }
  }
  if (indexed.length === 0) return null;
  indexed
    .map((p, i) => [p, i] as [[number, number], number])
    .sort((a, b) => (a[0][0] !== b[0][0] ? a[0][0] - b[0][0] : a[1] - b[1]));
  indexed.sort((a, b) => a[0] - b[0]); // stable in ES2019+, matching Python's sort
  return indexed.map(([, v]) => v);
}

/** Ascending upper bounds (bpm) + their basis ("settings" | "file:hr_zone"). */
export function hrZoneBounds(
  settings: AthleteSettings | null,
  messages: readonly Message[] | null = null,
): [readonly number[] | null, string | null] {
  if (settings?.hrZoneBounds && settings.hrZoneBounds.length > 0) {
    return [settings.hrZoneBounds, "settings"];
  }
  const bounds = boundsFromMessages(messages, "hr_zone", "high_bpm");
  if (bounds && bounds.length > 0) return [bounds, "file:hr_zone"];
  return [null, null];
}

/** Ascending upper bounds (W) + their basis ("settings" | "file:power_zone"). */
export function powerZoneBounds(
  settings: AthleteSettings | null,
  messages: readonly Message[] | null = null,
): [readonly number[] | null, string | null] {
  if (settings?.powerZoneBounds && settings.powerZoneBounds.length > 0) {
    return [settings.powerZoneBounds, "settings"];
  }
  const bounds = boundsFromMessages(messages, "power_zone", "high_value");
  if (bounds && bounds.length > 0) return [bounds, "file:power_zone"];
  return [null, null];
}
