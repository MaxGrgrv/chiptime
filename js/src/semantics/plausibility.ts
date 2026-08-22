/**
 * GPS plausibility gates (taxonomy #51/#53/#57).
 *
 * Twin of `python/src/chiptime/semantics/plausibility.py`. Lenient drops with
 * provenance; forensic annotates without dropping (ADR-0003 §3). Sustained jumps
 * (tunnels, #54) are never dropped — only physically-impossible bounce patterns are.
 *
 * This module contains the port's only transcendental math on a canonical-output
 * path. Measured at F36 over the 54 real position pairs in the `gps/*` corpus:
 * 53 of 54 haversine results are bit-identical between CPython's libm and V8, and
 * the outlier differs by 5.7e-14 m — one ULP, on a value that is thresholded and
 * then rounded to one decimal place (ADR-0009 §6).
 */

import type { Action, ProvenanceEntry } from "../errors.js";
import { type Session, getStream } from "../model.js";
import { pyFloatStr, pyRoundN } from "../numeric.js";

/** m/s ceilings per sport (generous: false negatives beat false drops). */
const SPEED_CEILINGS: Readonly<Record<string, number>> = {
  running: 12.5,
  walking: 8.0,
  hiking: 8.0,
  swimming: 4.0,
  cycling: 42.0,
};
const DEFAULT_CEILING = 55.0;

function radians(deg: number): number {
  return (deg * Math.PI) / 180;
}

function haversineM(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const rlat1 = radians(lat1);
  const rlat2 = radians(lat2);
  const dlat = rlat2 - rlat1;
  const dlon = radians(lon2 - lon1);
  const a = Math.sin(dlat / 2) ** 2 + Math.cos(rlat1) * Math.cos(rlat2) * Math.sin(dlon / 2) ** 2;
  return 12742000.0 * Math.asin(Math.sqrt(a));
}

export function gatePositions(
  s: Session,
  options: { forensic: boolean; virtual: boolean; provenance: ProvenanceEntry[]; scope: string },
): void {
  const { forensic, virtual, provenance, scope } = options;
  const lat = getStream(s.records, "position_lat");
  const lon = getStream(s.records, "position_long");
  if (lat === undefined || lon === undefined) return;
  if (virtual) {
    provenance.push({
      code: "VIRTUAL_GPS_EXEMPT",
      action: "ignored",
      scope,
      detail: "virtual-world coordinates (Zwift class); plausibility gate skipped (taxonomy #57)",
      byteOffset: null,
      data: {},
    });
    return;
  }

  const times = s.records.time;
  const ceiling = SPEED_CEILINGS[s.sport] ?? DEFAULT_CEILING;

  // Null Island (#51): exact (0,0) pairs are absence, not the Gulf of Guinea.
  const nullIsland: number[] = [];
  for (let i = 0; i < times.length; i++) {
    if (lat.values[i] === 0 && lon.values[i] === 0) nullIsland.push(i);
  }
  const nullSet = new Set(nullIsland);

  // Bounce spikes (#53): impossible in AND out, plausible if skipped.
  const fixes: [number, number, number][] = [];
  for (let i = 0; i < times.length; i++) {
    const la = lat.values[i];
    const lo = lon.values[i];
    if (typeof la === "number" && typeof lo === "number" && !nullSet.has(i) && times[i] !== null) {
      fixes.push([i, la, lo]);
    }
  }

  const spikes: [number, number][] = [];
  for (let k = 1; k < fixes.length - 1; k++) {
    const [i0, la0, lo0] = fixes[k - 1] as [number, number, number];
    const [i1, la1, lo1] = fixes[k] as [number, number, number];
    const [i2, la2, lo2] = fixes[k + 1] as [number, number, number];
    const t0 = times[i0] as number;
    const t1 = times[i1] as number;
    const t2 = times[i2] as number;
    const dtIn = t1 - t0;
    const dtOut = t2 - t1;
    const dtSkip = t2 - t0;
    if (dtIn <= 0 || dtOut <= 0 || dtSkip <= 0) continue;
    // Prefilter: 1 degree <= 111.32 km on either axis, so this bound can only
    // OVERestimate speed — skipping is always safe.
    const vInMax = (111320.0 * (Math.abs(la1 - la0) + Math.abs(lo1 - lo0))) / dtIn;
    if (vInMax <= ceiling) continue;
    const vIn = haversineM(la0, lo0, la1, lo1) / dtIn;
    const vOut = haversineM(la1, lo1, la2, lo2) / dtOut;
    const vSkip = haversineM(la0, lo0, la2, lo2) / dtSkip;
    if (vIn > ceiling && vOut > ceiling && vSkip <= ceiling) {
      spikes.push([i1, Math.max(vIn, vOut)]);
    }
  }

  const action: Action = forensic ? "ignored" : "dropped";
  if (nullIsland.length > 0) {
    if (!forensic) {
      for (const i of nullIsland) {
        lat.values[i] = null;
        lon.values[i] = null;
      }
    }
    provenance.push({
      code: "NULL_ISLAND_DROPPED",
      action,
      scope,
      detail: `${nullIsland.length} record(s) at exactly (0,0) ${forensic ? "flagged" : "nulled"} (taxonomy #51)`,
      byteOffset: null,
      data: { count: nullIsland.length },
    });
  }
  if (spikes.length > 0) {
    // 0.1 rounding: the determinism guard that makes the libm/V8 ULP difference
    // unobservable. pyRoundN, not toFixed — ties go to even.
    let worstRaw = Number.NEGATIVE_INFINITY;
    for (const [, v] of spikes) if (v > worstRaw) worstRaw = v;
    const worst = pyRoundN(worstRaw, 1);
    if (!forensic) {
      for (const [i] of spikes) {
        lat.values[i] = null;
        lon.values[i] = null;
      }
    }
    provenance.push({
      code: "GPS_SPIKES_DROPPED",
      action,
      scope,
      // pyFloatStr: Python prints an integral float as "55.0"; String(55) gives "55".
      detail:
        `${spikes.length} bounce spike(s) implying up to ${pyFloatStr(worst)} m/s ` +
        `${forensic ? "flagged" : "removed"} (sport ceiling ${pyFloatStr(ceiling)} m/s, taxonomy #53)`,
      byteOffset: null,
      data: { count: spikes.length, worst_mps: worst, ceiling_mps: ceiling },
    });
  }
}
