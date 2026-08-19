"""Reconciliation, rebuild, and multisport tests (#75/#92/#93/#95/#96/#97)."""

import build_fit

import chiptime


def test_summary_mismatch_discrepancies() -> None:
    result = chiptime.parse(build_fit.summary_mismatch())
    s = result.activity.sessions[0]
    fields = {d.field: d for d in s.discrepancies}
    assert "elapsed_time_s" in fields and fields["elapsed_time_s"].declared == 200.0
    assert "distance_m" in fields and abs(fields["distance_m"].derived - 991.27) < 0.01
    assert "avg.power" in fields and fields["avg.power"].derived == 200.0
    assert "ascent_m" in fields  # declared 90 vs ~9 derived (3m hysteresis)
    codes = {w.code for w in result.warnings}
    assert "SUMMARY_AVG_EXCEEDS_MAX" in codes  # avg power 250 > max 240


def test_clean_seed_has_no_discrepancies() -> None:
    result = chiptime.parse(build_fit.ride_smooth())
    assert result.activity.sessions[0].discrepancies == []


def test_session_rebuild() -> None:
    result = chiptime.parse(build_fit.no_session())
    a = result.activity
    s = a.sessions[0]
    assert s.rebuilt and s.declared is None
    assert s.sport == "cycling"  # from the sport message
    assert s.derived.elapsed_time_s == 89.0
    assert s.derived.timer_time_s == 89.0  # start event, synthesized stop
    assert any(p.code == "SESSION_REBUILT" for p in result.provenance)
    assert any(p.code == "TIMER_STOP_SYNTHESIZED" for p in result.provenance)


def test_no_records_no_fake_sessions() -> None:
    result = chiptime.parse(build_fit.string_edges())
    assert result.activity is not None
    assert result.activity.sessions == []  # honest emptiness (#16 class)


def test_multisport_bounding() -> None:
    result = chiptime.parse(build_fit.multisport())
    a = result.activity
    assert [s.sport for s in a.sessions] == ["swimming", "transition", "cycling"]
    assert [s.records.n for s in a.sessions] == [100, 30, 200]
    assert a.sessions[0].sub_sport == "open_water"
    assert len(a.sessions[0].laps) == 1 and len(a.sessions[2].laps) == 1
    speeds = a.sessions[2].records.stream("speed")
    assert speeds is not None and speeds.values[0] == 10.0
    assert not any(w.code == "NUM_SESSIONS_MISMATCH" for w in result.warnings)


def test_zero_duration_flagged() -> None:
    result = chiptime.parse(build_fit.zero_duration())
    assert any(w.code == "ZERO_DURATION_SESSION" for w in result.warnings)
