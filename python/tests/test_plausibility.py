"""GPS plausibility tests: bounces vs tunnels, Null Island, virtual exemption."""

import build_fit

import chiptime


def test_bounce_dropped_tunnel_kept() -> None:
    result = chiptime.parse(build_fit.gps_spikes())
    s = result.activity.sessions[0]
    lat = s.records.stream("position_lat")
    assert lat is not None
    assert lat.values[10] is None and lat.values[25] is None  # bounces dropped
    assert lat.values[32] is not None and lat.values[33] is not None  # tunnel kept
    prov = next(p for p in result.provenance if p.code == "GPS_SPIKES_DROPPED")
    assert prov.data["count"] == 2 and prov.action == "dropped"
    assert prov.data["ceiling_mps"] == 12.5  # running


def test_forensic_flags_but_keeps() -> None:
    result = chiptime.parse(build_fit.gps_spikes(), mode="forensic")
    s = result.activity.sessions[0]
    lat = s.records.stream("position_lat")
    assert lat is not None and lat.values[10] is not None  # kept
    prov = next(p for p in result.provenance if p.code == "GPS_SPIKES_DROPPED")
    assert prov.action == "ignored"


def test_null_island() -> None:
    result = chiptime.parse(build_fit.null_island())
    s = result.activity.sessions[0]
    lat = s.records.stream("position_lat")
    lon = s.records.stream("position_long")
    assert lat is not None and lon is not None
    assert lat.values[2] is None and lon.values[3] is None  # (0,0) nulled
    assert lat.values[5] is None  # sentinel from decode
    assert lat.values[0] is not None and lat.values[11] is not None
    assert any(p.code == "NULL_ISLAND_DROPPED" for p in result.provenance)


def test_virtual_gps_untouched() -> None:
    result = chiptime.parse(build_fit.virtual_gps())
    s = result.activity.sessions[0]
    lat = s.records.stream("position_lat")
    assert lat is not None and all(v is not None for v in lat.values)
    assert any(p.code == "VIRTUAL_GPS_EXEMPT" for p in result.provenance)
    assert not any(p.code == "GPS_SPIKES_DROPPED" for p in result.provenance)


def test_treadmill_no_false_positives() -> None:
    result = chiptime.parse(build_fit.treadmill_jump())
    assert result.ok
    assert not any(
        p.code in ("GPS_SPIKES_DROPPED", "NULL_ISLAND_DROPPED") for p in result.provenance
    )
    s = result.activity.sessions[0]
    assert s.sub_sport == "treadmill"
    dist = s.records.stream("distance")
    assert dist is not None and dist.values[-1] == 1200.0  # correction preserved
