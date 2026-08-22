/**
 * Athlete-supplied thresholds — the only door for zone/threshold context.
 *
 * Twin of `python/src/chiptime/metrics/settings.py`. ADR-0008 §4: thresholds come
 * from the user or the file, never from inference. Everything is optional; analyses
 * that need an absent threshold are omitted with a note rather than estimated.
 */

/** All fields optional; absent means "don't compute what needs it". */
export interface AthleteSettings {
  ftpW?: number | null;
  thresholdPaceSPerKm?: number | null;
  cssSPer100m?: number | null;
  maxHr?: number | null;
  restingHr?: number | null;
  lthr?: number | null;
  /** Ascending upper bounds. */
  hrZoneBounds?: readonly number[] | null;
  /** Ascending upper bounds. */
  powerZoneBounds?: readonly number[] | null;
  /** "male" | "female" — TRIMP coefficient. */
  sex?: string | null;
}
