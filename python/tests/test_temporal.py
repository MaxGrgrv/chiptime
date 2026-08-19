"""Temporal tests: timer machine, gap classification, ordering, sanity flags."""

import build_fit

import chiptime


def test_gap_classification_full_zoo() -> None:
    result = chiptime.parse(build_fit.gaps_timers())
    a = result.activity
    assert a is not None
    kinds = [(g.kind, round(g.duration_s)) for g in a.gaps]
    assert ("manual_stop", 301) in kinds
    assert ("smart_recording", 26) in kinds
    assert ("unknown", 46) in kinds
    assert ("post_timer", 60) in kinds
    s = a.sessions[0]
    assert s.derived.timer_time_s == 210.0  # 60 + 150
    assert s.derived.elapsed_time_s == 580.0
    assert s.derived.moving_time_s is not None
    manual = next(g for g in a.gaps if g.kind == "manual_stop")
    assert "timer stop" in manual.evidence


def test_missing_final_stop_synthesized() -> None:
    result = chiptime.parse(build_fit.missing_final_stop())
    assert any(p.code == "TIMER_STOP_SYNTHESIZED" for p in result.provenance)
    s = result.activity.sessions[0]
    assert s.derived.timer_time_s == 29.0  # start → last record


def test_nonmonotonic_sorted_with_provenance() -> None:
    result = chiptime.parse(build_fit.nonmonotonic())
    s = result.activity.sessions[0]
    ts = [t.timestamp() for t in s.records.time if t is not None]
    assert ts == sorted(ts)  # sorted timeline
    hr = s.records.stream("heart_rate")
    assert hr is not None
    # duplicate second (t0+3): original file order preserved among equals:
    # 123 (original), then 200, then 201
    assert hr.values[3:6] == [123, 200, 201]
    assert any(p.code == "RECORDS_REORDERED" for p in result.provenance)
    # lossless layer untouched: message order in decode remains file order
    msgs = list(chiptime.iter_messages(build_fit.nonmonotonic()))
    raw_hr = [m.get("heart_rate") for m in msgs if m.name == "record"]
    assert raw_hr[5:8] == [125, 200, 201]


def test_zwift_local_timestamp_bug() -> None:
    result = chiptime.parse(build_fit.zwift_local1989())
    a = result.activity
    assert a is not None and a.utc_offset_s is None
    assert any(w.code == "LOCAL_TIMESTAMP_IMPLAUSIBLE" for w in result.warnings)
    assert any(w.code == "RELATIVE_TIMESTAMP" for w in result.warnings)  # decode layer too
    assert a.sessions[0].sub_sport == "virtual_activity"


def test_healthy_utc_offset() -> None:
    result = chiptime.parse(build_fit.ride_smooth())
    assert result.activity is not None
    assert result.activity.utc_offset_s == 7200  # seed writes local = UTC+2


def test_pre_2010_flagged_timeline_kept() -> None:
    result = chiptime.parse(build_fit.old_timestamps())
    assert any(w.code == "UNRELIABLE_ABSOLUTE_TIME" for w in result.warnings)
    s = result.activity.sessions[0]
    assert s.derived.elapsed_time_s == 9.0  # relative timeline intact
    assert s.records.time[0] is not None and s.records.time[0].year == 2005
