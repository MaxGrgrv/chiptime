/**
 * Sport profiles — the table that knows how each sport measures itself.
 *
 * Twin of `python/src/chiptime/metrics/sports.py`. Profiles are data, not
 * subclasses (ADR-0008 §2).
 */

import { type Session, getStream, presentCount } from "../model.js";

export type PaceStyle = "per_km" | "per_100m" | "per_500m" | "speed";

/**
 * Below this, a running cadence is per-leg strides/min on many devices (taxonomy
 * #66); display convention is steps/min, so we double and label.
 */
export const RUN_PER_LEG_CADENCE_MAX = 130.0;

export interface SportProfile {
  readonly key: string;
  readonly paceStyle: PaceStyle;
  readonly primary: "power" | "speed";
  readonly cadenceUnits: string;
  readonly cadenceDoubleIfPerLeg: boolean;
  readonly distanceFromLengths: boolean;
}

function sp(
  key: string,
  paceStyle: PaceStyle,
  primary: "power" | "speed",
  cadenceUnits: string,
  opts: { double?: boolean; lengths?: boolean } = {},
): SportProfile {
  return {
    key,
    paceStyle,
    primary,
    cadenceUnits,
    cadenceDoubleIfPerLeg: opts.double ?? false,
    distanceFromLengths: opts.lengths ?? false,
  };
}

export const RUNNING = sp("running", "per_km", "speed", "spm", { double: true });
export const CYCLING = sp("cycling", "speed", "power", "rpm");
export const POOL_SWIM = sp("pool_swim", "per_100m", "speed", "strokes/min", { lengths: true });
export const OPEN_WATER_SWIM = sp("open_water_swim", "per_100m", "speed", "strokes/min");
export const ROWING = sp("rowing", "per_500m", "power", "strokes/min");
export const HIKING = sp("hiking", "per_km", "speed", "spm");
export const XC_SKIING = sp("cross_country_skiing", "per_km", "speed", "spm");
export const GENERIC = sp("generic", "per_km", "speed", "rpm");

const BY_SPORT: Readonly<Record<string, SportProfile>> = {
  running: RUNNING,
  cycling: CYCLING,
  rowing: ROWING,
  hiking: HIKING,
  walking: HIKING,
  cross_country_skiing: XC_SKIING,
};

/**
 * Resolve (sport, subSport) → profile; unknown sports get GENERIC
 * (correct-but-shallow beats wrong-but-specific).
 */
export function profileFor(session: Session): SportProfile {
  const sport = (session.sport ?? "").toLowerCase();
  const sub = (session.subSport ?? "").toLowerCase();
  if (sport === "swimming") return sub === "open_water" ? OPEN_WATER_SWIM : POOL_SWIM;
  if (sub === "indoor_rowing" || (sport === "fitness_equipment" && sub.includes("row"))) {
    return ROWING;
  }
  return BY_SPORT[sport] ?? GENERIC;
}

/**
 * The intensity signal actually available: profile preference constrained by which
 * streams exist. Returns [kind, streamName]; kind is "power" | "speed" | "none".
 */
export function primarySignal(session: Session): [string, string | null] {
  const p = profileFor(session);
  if (p.primary === "power") {
    const s = getStream(session.records, "power");
    if (s !== undefined && presentCount(s) > 0) return ["power", "power"];
  }
  for (const name of ["enhanced_speed", "speed"]) {
    const s = getStream(session.records, name);
    if (s !== undefined && presentCount(s) > 0) return ["speed", name];
  }
  return ["none", null];
}

/** [value, units, note]. The doubling heuristic is labeled, never silent. */
export function cadenceDisplay(
  avgCadence: number | null,
  profile: SportProfile,
): [number | null, string, string | null] {
  if (avgCadence === null) return [null, profile.cadenceUnits, null];
  if (profile.cadenceDoubleIfPerLeg && avgCadence < RUN_PER_LEG_CADENCE_MAX) {
    return [avgCadence * 2.0, profile.cadenceUnits, "doubled_per_leg_cadence"];
  }
  return [avgCadence, profile.cadenceUnits, null];
}
