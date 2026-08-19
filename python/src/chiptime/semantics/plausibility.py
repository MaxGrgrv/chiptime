"""GPS plausibility gates (taxonomy #51/#53/#57).

Lenient drops with provenance; forensic annotates without dropping
(ADR-0003 §3). Sustained jumps (tunnels, #54) are never dropped — only
physically-impossible bounce patterns are.
"""

from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from chiptime.errors import Action, ProvenanceEntry
from chiptime.model import Session

# m/s ceilings per sport (generous: false negatives beat false drops)
SPEED_CEILINGS: dict[str, float] = {
    "running": 12.5,
    "walking": 8.0,
    "hiking": 8.0,
    "swimming": 4.0,
    "cycling": 42.0,
}
DEFAULT_CEILING = 55.0


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1, rlat2 = radians(lat1), radians(lat2)
    dlat = rlat2 - rlat1
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return 12742000.0 * asin(sqrt(a))


def gate_positions(
    s: Session,
    *,
    forensic: bool,
    virtual: bool,
    provenance: list[ProvenanceEntry],
    scope: str,
) -> None:
    lat = s.records.stream("position_lat")
    lon = s.records.stream("position_long")
    if lat is None or lon is None:
        return
    if virtual:
        provenance.append(
            ProvenanceEntry(
                "VIRTUAL_GPS_EXEMPT",
                "ignored",
                scope,
                "virtual-world coordinates (Zwift class); plausibility gate skipped (taxonomy #57)",
            )
        )
        return

    times = s.records.time
    ceiling = SPEED_CEILINGS.get(s.sport, DEFAULT_CEILING)

    # Null Island (#51): exact (0,0) pairs are absence, not the Gulf of Guinea.
    null_island = [i for i in range(len(times)) if lat.values[i] == 0.0 and lon.values[i] == 0.0]
    # Bounce spikes (#53): impossible in AND out, plausible if skipped.
    fixes = [
        (i, float(lat.values[i]), float(lon.values[i]))
        for i in range(len(times))
        if isinstance(lat.values[i], float)
        and isinstance(lon.values[i], float)
        and i not in set(null_island)
        and times[i] is not None
    ]
    spikes: list[tuple[int, float]] = []
    for k in range(1, len(fixes) - 1):
        i0, la0, lo0 = fixes[k - 1]
        i1, la1, lo1 = fixes[k]
        i2, la2, lo2 = fixes[k + 1]
        t0, t1, t2 = times[i0], times[i1], times[i2]
        assert t0 is not None and t1 is not None and t2 is not None
        dt_in = (t1 - t0).total_seconds()
        dt_out = (t2 - t1).total_seconds()
        dt_skip = (t2 - t0).total_seconds()
        if dt_in <= 0 or dt_out <= 0 or dt_skip <= 0:
            continue
        # F20 prefilter: 1 degree <= 111.32 km on either axis, so this bound
        # can only OVERestimate speed — skipping is always safe.
        v_in_max = 111320.0 * (abs(la1 - la0) + abs(lo1 - lo0)) / dt_in
        if v_in_max <= ceiling:
            continue
        v_in = _haversine_m(la0, lo0, la1, lo1) / dt_in
        v_out = _haversine_m(la1, lo1, la2, lo2) / dt_out
        v_skip = _haversine_m(la0, lo0, la2, lo2) / dt_skip
        if v_in > ceiling and v_out > ceiling and v_skip <= ceiling:
            spikes.append((i1, max(v_in, v_out)))

    action: Action = "ignored" if forensic else "dropped"
    if null_island:
        if not forensic:
            for i in null_island:
                lat.values[i] = None
                lon.values[i] = None
        provenance.append(
            ProvenanceEntry(
                "NULL_ISLAND_DROPPED",
                action,
                scope,
                f"{len(null_island)} record(s) at exactly (0,0)"
                f" {'flagged' if forensic else 'nulled'} (taxonomy #51)",
                data={"count": len(null_island)},
            )
        )
    if spikes:
        worst = round(max(v for _, v in spikes), 1)  # 0.1 rounding: determinism guard
        if not forensic:
            for i, _ in spikes:
                lat.values[i] = None
                lon.values[i] = None
        provenance.append(
            ProvenanceEntry(
                "GPS_SPIKES_DROPPED",
                action,
                scope,
                f"{len(spikes)} bounce spike(s) implying up to {worst} m/s"
                f" {'flagged' if forensic else 'removed'} (sport ceiling"
                f" {ceiling} m/s, taxonomy #53)",
                data={"count": len(spikes), "worst_mps": worst, "ceiling_mps": ceiling},
            )
        )
