"""Tier-2 depth tests: CRC triage, components, accumulators, subfields, flags."""

import build_fit
import corrupt

import chiptime


def test_crc_triage_unterminated() -> None:
    data = corrupt.zero_file_crc(build_fit.run_basic())
    result = chiptime.parse(data)
    w = next(w for w in result.warnings if w.code == "FIT_CRC_MISMATCH")
    assert "unterminated-write" in w.detail


def test_crc_triage_inplace() -> None:
    data = corrupt.break_file_crc(build_fit.run_basic())
    result = chiptime.parse(data)
    w = next(w for w in result.warnings if w.code == "FIT_CRC_MISMATCH")
    assert "in-place corruption" in w.detail


def test_csd_expansion_with_rollover() -> None:
    result = chiptime.parse(build_fit.csd_legacy())
    s = result.activity.sessions[0]
    speed = s.records.stream("speed")
    assert speed is not None and speed.values[0] == 3.0
    dist = s.records.stream("distance")
    assert dist is not None
    diffs = [b - a for a, b in zip(dist.values, dist.values[1:], strict=False)]
    assert all(abs(d - 3.0) < 0.01 for d in diffs)  # monotone through the 256m wrap
    assert any(p.code == "FIELD_RAW_SALVAGED" and "expanded" in p.detail for p in result.provenance)


def test_accumulator_unwrap() -> None:
    result = chiptime.parse(build_fit.accumulator_wrap())
    s = result.activity.sessions[0]
    acc = s.records.stream("accumulated_power")
    assert acc is not None
    vals = acc.values
    assert vals[0] == 4294967000 and vals[1] == 4294967290
    assert vals[2] == 150 + 2**32 and vals[3] == 400 + 2**32
    d = result.to_dict()  # >2^53? no — but must serialize fine
    assert d


def test_event_subfield_and_auto_pause() -> None:
    result = chiptime.parse(build_fit.event_subfields())
    events = [m for m in result.messages if m.name == "event"]
    pause = next(m for m in events if m.get("event_type") == "stop")
    assert pause.get("timer_trigger") == "auto"
    assert pause.get("data") == 1  # original field retained
    a = result.activity
    assert any(g.kind == "auto_pause" for g in a.gaps)


def test_sensor_flags_all_fire_nothing_edited() -> None:
    result = chiptime.parse(build_fit.sensor_anomalies())
    codes = {w.code for w in result.warnings}
    assert {
        "HR_IMPLAUSIBLE",
        "HR_FLATLINE",
        "POWER_IMPLAUSIBLE",
        "DISTANCE_DECREASES",
        "DISTANCE_RESET",
    } <= codes
    s = result.activity.sessions[0]
    hr = s.records.stream("heart_rate")
    power = s.records.stream("power")
    assert hr.values[5] == 250  # flagged, NOT removed (#62)
    assert power.values[10] == 4000  # sprints are real until proven otherwise (#63)


def test_pool_swim_checks() -> None:
    result = chiptime.parse(build_fit.pool_swim())
    codes = {w.code for w in result.warnings}
    assert "POOL_ZERO_LENGTH" in codes
    assert "POOL_LENGTH_IMPLAUSIBLE" in codes
    s = result.activity.sessions[0]
    assert len(s.lengths) == 11
    assert s.lengths[0].swim_stroke == "freestyle"


def test_zero_duration_lap_flagged() -> None:
    result = chiptime.parse(build_fit.zero_duration_lap())
    assert any(w.code == "LAP_ZERO_DURATION" for w in result.warnings)
    assert len(result.activity.sessions[0].laps) == 3  # kept, not dropped


def test_empty_shell_gets_honest_error() -> None:
    """F17 / taxonomy #16: ok=false must never come with empty errors."""
    b = build_fit.FitBuilder()
    data = b.build()  # header + CRC, zero messages — 16 bytes, seen in the wild
    assert len(data) == 16
    result = chiptime.parse(data)
    assert not result.ok
    assert result.errors and result.errors[0].code == "FIT_NO_CONTENT"
    assert result.errors[0].suggestion is not None
    strict = chiptime.parse(data, mode="strict")  # spec-legal: no raise, same honesty
    assert not strict.ok and strict.errors[0].code == "FIT_NO_CONTENT"


def test_distance_frozen_not_flagged_for_swims() -> None:
    """F17: swims legitimately freeze distance between lengths (#56/#73)."""
    b = build_fit.FitBuilder()
    t0 = build_fit.fit_ts(build_fit.T0)
    b.define(0, build_fit.FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(1, build_fit.RECORD, [(253, "uint32", 1), (5, "uint32", 1), (6, "uint16", 1)])
    for i in range(40):
        b.data(1, t0 + i, 2500 * (i // 20), 1500)  # distance frozen 20s at a time
    b.define(
        6,
        build_fit.SESSION,
        [
            (253, "uint32", 1),
            (254, "uint16", 1),
            (0, "enum", 1),
            (1, "enum", 1),
            (2, "uint32", 1),
            (5, "enum", 1),
            (6, "enum", 1),
            (7, "uint32", 1),
            (8, "uint32", 1),
            (9, "uint32", 1),
        ],
    )
    b.data(6, t0 + 40, 0, 8, 1, t0, 5, 17, 40000, 40000, 5000)  # swimming
    result = chiptime.parse(b.build())
    assert not any(w.code == "DISTANCE_FROZEN" for w in result.warnings)


def _dist_frozen_file(n_frozen: int, speed_raw: int = 8333) -> bytes:
    b = build_fit.FitBuilder()
    t0 = build_fit.fit_ts(build_fit.T0)
    b.define(0, build_fit.FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(1, build_fit.RECORD, [(253, "uint32", 1), (5, "uint32", 1), (6, "uint16", 1)])
    dist = 0
    for i in range(120):
        if not 40 <= i < 40 + n_frozen:
            dist += 833
        b.data(1, t0 + i, dist, speed_raw)
    return b.build()


def test_distance_frozen_requires_long_run() -> None:
    """F19 real-ride finding: junction stops (short freezes) are benign;
    only a sustained run at speed is a dead sensor."""
    short = chiptime.parse(_dist_frozen_file(15))
    assert not any(w.code == "DISTANCE_FROZEN" for w in short.warnings)
    long_run = chiptime.parse(_dist_frozen_file(45))
    assert any(w.code == "DISTANCE_FROZEN" for w in long_run.warnings)
