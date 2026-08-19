"""Semantic model tests: streams, zero-vs-null, enhanced pairs, dev promotion."""

import json

import build_fit

import chiptime


def test_ride_smooth_model() -> None:
    result = chiptime.parse(build_fit.ride_smooth())
    a = result.activity
    assert a is not None
    assert len(a.sessions) == 1
    s = a.sessions[0]
    assert s.sport == "cycling"
    assert s.records.n == 120
    power = s.records.stream("power")
    assert power is not None
    assert power.values[30] == 0  # coasting: REAL zero (taxonomy #64)
    assert power.values[52] is None  # dropout: absent (taxonomy #68)
    assert power.present_count == 114
    assert s.declared is not None and s.declared.elapsed_time_s == 120.0
    assert s.derived.elapsed_time_s == 119.0  # 120 records at 1 Hz span 119 s
    assert s.derived.max["power"] == 220.0
    assert len(s.laps) == 1
    assert s.laps[0].end_time is not None and s.laps[0].start_time is not None
    assert (s.laps[0].end_time - s.laps[0].start_time).total_seconds() == 120.0
    assert a.device is not None and a.device.manufacturer == "garmin"


def test_record_messages_fold_into_streams() -> None:
    result = chiptime.parse(build_fit.ride_smooth())
    d = result.to_dict()
    part = d["parts"][0]
    assert part["activity"] is not None
    assert all(m["name"] != "record" for m in part["messages"])
    streams = part["activity"]["sessions"][0]["records"]["streams"]
    assert streams["power"]["values"][30] == 0
    assert streams["power"]["values"][52] is None
    # canonical JSON stays valid JSON with the model embedded
    json.loads(result.to_canonical_json())


def test_enhanced_pairs_merge() -> None:
    result = chiptime.parse(build_fit.enhanced_pairs())
    s = result.activity.sessions[0]
    speed = s.records.stream("speed")
    assert speed is not None
    assert s.records.stream("enhanced_speed") is None  # never both (taxonomy #28)
    assert speed.values == [8.333, 70.0, 71.0]  # enhanced wins; fills base-absent
    alt = s.records.stream("altitude")
    assert alt is not None and alt.values == [12.0, 105.0, 106.0]
    assert any(p.code == "ENHANCED_PAIR_MERGED" for p in result.provenance)
    assert any(w.code == "ENHANCED_PAIR_DISAGREES" for w in result.warnings)


def test_dev_stream_promotion() -> None:
    result = chiptime.parse(build_fit.dev_fields_stryd())
    s = result.activity.sessions[0]
    rp = s.records.stream("running_power")
    assert rp is not None
    assert rp.source == "developer:stryd"
    assert rp.values == [250, 251, 252, 253]
    lss = s.records.stream("leg_spring_stiffness")
    assert lss is not None and lss.values[0] == 10.3


def test_summary_only_empty_records() -> None:
    result = chiptime.parse(build_fit.summary_only())
    s = result.activity.sessions[0]
    assert s.records.n == 0
    assert s.declared is not None and s.declared.distance_m == 10000.0
    assert s.derived.elapsed_time_s is None  # honestly not derivable from zero records
