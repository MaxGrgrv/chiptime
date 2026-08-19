"""F25: load estimators, insight codes, report builder, analyze CLI."""

from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from chiptime import metrics
from chiptime.cli import main
from chiptime.model import Records, Session, Stream

BASE = datetime(2026, 6, 1, 8, 0, 0, tzinfo=UTC)
REPO = Path(__file__).resolve().parents[2]


def _session(sport: str, sub: str | None = None, **streams: list[object]) -> Session:
    n = max((len(v) for v in streams.values()), default=0)
    rec = Records(
        time=[BASE + timedelta(seconds=i) for i in range(n)],
        streams={k: Stream(k, None, list(v)) for k, v in streams.items()},
    )
    return Session(
        sport=sport, sub_sport=sub, start_time=BASE if n else None, end_time=None, records=rec
    )


# --- load math ----------------------------------------------------------


def test_weighted_power_constant_equals_avg() -> None:
    assert metrics.weighted_avg_power([200.0] * 120) == 200.0
    assert metrics.weighted_avg_power([200.0] * 10) is None  # under one window


def test_weighted_power_exceeds_avg_on_surges() -> None:
    vals: list[object] = ([100.0] * 60 + [400.0] * 60) * 4
    wap = metrics.weighted_avg_power(vals)
    avg = 250.0
    assert wap is not None and wap > avg  # 4th-power weighting rewards surges
    # zeros are real (coasting) and pull the weighted value down
    with_coast = metrics.weighted_avg_power([0.0] * 120 + [200.0] * 120)
    assert with_coast is not None and with_coast < 200.0
    # nulls (dropouts) are skipped, not zero-filled
    with_nulls = metrics.weighted_avg_power([None] * 120 + [200.0] * 120)
    assert with_nulls == 200.0


def test_trimp_matches_banister_formula() -> None:
    times = [BASE + timedelta(seconds=i) for i in range(3601)]
    hr: list[object] = [150.0] * 3601
    got = metrics.trimp(times, hr, resting_hr=50.0, max_hr=190.0)
    hrr = (150.0 - 50.0) / 140.0
    want = 60.0 * hrr * 0.64 * math.exp(1.92 * hrr)
    assert got is not None and abs(got - want) < 0.5
    female = metrics.trimp(times, hr, resting_hr=50.0, max_hr=190.0, sex="female")
    assert female is not None and female < got  # 1.67 coefficient
    assert metrics.trimp(times, hr, resting_hr=190.0, max_hr=50.0) is None


def test_load_ladder_and_bases() -> None:
    ride = _session("cycling", power=[250.0] * 3600)
    with_ftp = metrics.workout_load(ride, metrics.AthleteSettings(ftp_w=250.0))
    assert with_ftp is not None and with_ftp.basis == "power+ftp"
    assert abs(with_ftp.value - 100.0) < 2.0  # ~1 h at threshold == 100 by definition
    hr_ride = _session("cycling", heart_rate=[150.0] * 3600)
    with_hr = metrics.workout_load(hr_ride, metrics.AthleteSettings(max_hr=190.0, resting_hr=50.0))
    assert with_hr is not None and "hr-trimp" in with_hr.basis
    assert "male-coefficient" in with_hr.basis  # sex unset -> labeled default
    assert metrics.workout_load(ride, None) is None
    assert metrics.workout_load(ride, metrics.AthleteSettings()) is None


def test_fitness_fatigue_form_ewma() -> None:
    d0 = date(2026, 6, 1)
    pts = metrics.fitness_fatigue_form([(d0, 100.0), (d0 + timedelta(days=2), 50.0)])
    assert len(pts) == 3  # missing day filled with 0 load
    k_fit = 1 - math.exp(-1 / 42.0)
    assert abs(pts[0].fitness - 100.0 * k_fit) < 1e-9
    assert pts[0].form == 0.0  # day one: no yesterday
    assert pts[1].load == 0.0
    assert pts[1].form == pts[0].fitness - pts[0].fatigue  # form lags a day
    assert pts[2].fitness > pts[1].fitness  # new load lifts fitness


# --- insights -----------------------------------------------------------


def test_negative_split_and_hr_drift_insights() -> None:
    n = 600
    speed: list[object] = [3.0] * (n // 2) + [3.3] * (n // 2)  # 10% faster 2nd half
    hr: list[object] = [140.0] * (n // 2) + [170.0] * (n // 2)
    s = _session("running", enhanced_speed=speed, heart_rate=hr)
    rep = metrics.analyze_session(s)
    codes = {i.code for i in rep.insights}
    assert "PACING_NEGATIVE_SPLIT" in codes
    assert "HR_DRIFT_HIGH" in codes  # speed up 10%, HR up 14% -> EF fell
    drift = next(i for i in rep.insights if i.code == "HR_DRIFT_HIGH")
    assert drift.evidence["drift_pct"] > 5.0


def test_coasting_insight_is_cycling_only() -> None:
    vals: list[object] = [0.0] * 40 + [200.0] * 60
    ride = metrics.analyze_session(_session("cycling", power=vals))
    assert "COASTING_HIGH" in {i.code for i in ride.insights}
    run = metrics.analyze_session(_session("running", power=vals))
    assert "COASTING_HIGH" not in {i.code for i in run.insights}


def test_report_zones_and_omissions() -> None:
    s = _session("cycling", power=[210.0] * 300, heart_rate=[150.0] * 300)
    bare = metrics.analyze_session(s)
    assert bare.hr_zones is None and bare.power_zones is None
    assert any(o.startswith("load:") for o in bare.omissions)
    assert any(o.startswith("hr_zones:") for o in bare.omissions)
    cfg = metrics.AthleteSettings(ftp_w=250.0, hr_zone_bounds=(115.0, 135.0, 155.0, 172.0, 188.0))
    rich = metrics.analyze_session(s, settings=cfg)
    assert rich.hr_zones is not None and rich.hr_zones["basis"] == "settings"
    assert sum(rich.hr_zones["seconds"]) > 0
    assert rich.load is not None and rich.load.basis == "power+ftp"
    assert not any(o.startswith("hr_zones") for o in rich.omissions)


def test_report_to_dict_is_json_ready() -> None:
    s = _session("running", enhanced_speed=[3.0] * 200, heart_rate=[150.0] * 200)
    d = metrics.analyze_session(s).to_dict()
    payload = json.dumps(d, sort_keys=True)  # raises if anything non-plain leaks
    assert '"profile": "running"' in payload or '"profile":"running"' in json.dumps(
        d, sort_keys=True, separators=(",", ":")
    )


def test_insight_codes_registry_covers_emitted_codes() -> None:
    assert set(metrics.INSIGHT_CODES) >= {
        "PACING_NEGATIVE_SPLIT",
        "PACING_POSITIVE_SPLIT",
        "HR_DRIFT_HIGH",
        "COASTING_HIGH",
        "WORKOUT_STRUCTURE",
    }


# --- CLI end-to-end -----------------------------------------------------


def test_cli_analyze_json(capsys: pytest.CaptureFixture[str]) -> None:
    src = REPO / "corpus" / "cases" / "clean" / "ride-smooth" / "input.fit"
    code = main(["analyze", str(src), "--json", "--ftp", "250"])
    out = capsys.readouterr().out
    report = json.loads(out)
    assert code in (0, 2)
    assert report["sessions"], "expected at least one session report"
    ses = report["sessions"][0]
    assert ses["sport"] == "cycling"
    assert ses["primary_signal"] in ("power", "speed")
    assert "insights" in ses and "omissions" in ses
    assert json.dumps(report, sort_keys=True) == json.dumps(  # deterministic dump
        json.loads(out), sort_keys=True
    )


def test_cli_analyze_text_and_zones(capsys: pytest.CaptureFixture[str]) -> None:
    src = REPO / "corpus" / "cases" / "clean" / "run-basic" / "input.fit"
    code = main(["analyze", str(src)])
    out = capsys.readouterr().out
    assert code in (0, 2)
    assert "session 1: running" in out


def test_cli_analyze_bad_bounds_is_usage_error() -> None:
    src = REPO / "corpus" / "cases" / "clean" / "run-basic" / "input.fit"
    try:
        main(["analyze", str(src), "--hr-zones", "188,115"])
        raise AssertionError("expected SystemExit 64")
    except SystemExit as e:
        assert e.code == 64


def test_sparse_hr_blocks_trimp_with_honest_omission() -> None:
    # HR present for only ~10% of samples: trimp would understate massively
    hr: list[object] = [150.0 if i % 10 == 0 else None for i in range(3600)]
    s = _session("swimming", heart_rate=hr)
    cfg = metrics.AthleteSettings(max_hr=190.0, resting_hr=50.0)
    assert metrics.workout_load(s, cfg) is None
    rep = metrics.analyze_session(s, settings=cfg)
    assert rep.load is None
    assert any("trimp would understate" in o for o in rep.omissions)
    cov = metrics.hr_coverage_fraction(s)
    assert cov is not None and cov < 0.2
