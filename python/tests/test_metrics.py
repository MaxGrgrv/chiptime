"""Metrics + HRV + pandas-bridge tests (F21). Real-file SWOLF when private
tier is present; synthetic fallbacks keep public CI meaningful."""

from pathlib import Path

import build_fit
import pytest

import chiptime
from chiptime import metrics


def test_core_never_imports_metrics_or_pandas() -> None:
    import subprocess
    import sys

    code = (
        "import sys, chiptime; "
        "bad = [m for m in sys.modules if m in ('pandas', 'chiptime.metrics')]; "
        "print(bad); sys.exit(1 if bad else 0)"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True)
    assert r.returncode == 0, r.stdout


def test_hrv_surfaced_in_model() -> None:
    result = chiptime.parse(build_fit.hrv_arrays())
    a = result.activity
    assert a is not None
    assert a.hrv_intervals_s == [0.5, 0.52, 0.53, 0.51, 0.54]
    d = result.to_dict()
    assert d["parts"][0]["activity"]["hrv_intervals_s"] == [0.5, 0.52, 0.53, 0.51, 0.54]


def test_mean_max_none_honesty() -> None:
    values = [200] * 50 + [None] * 20 + [300] * 50
    mm = metrics.mean_max(values, [10, 40, 120, 999])
    assert mm[10] == 300.0
    assert mm[40] == 300.0
    assert mm[999] is None  # window longer than data
    assert mm[120] is None  # 20/120 missing > 10% → honest None


def test_mean_max_prefers_best_window() -> None:
    values = [100] * 30 + [400] * 10 + [100] * 30
    assert metrics.mean_max(values, [10])[10] == 400.0
    assert metrics.mean_max(values, [20])[20] == 250.0  # 10x400 + 10x100


def test_time_in_zones() -> None:
    result = chiptime.parse(build_fit.ride_smooth())
    s = result.activity.sessions[0]
    power = s.records.stream("power")
    zones = metrics.time_in_zones(s.records.time, power.values, [100.0, 200.0])
    assert len(zones) == 3
    # 119 counted intervals; power alternates 180/220 with 0s and dropouts
    assert sum(zones) <= 119.0
    assert zones[0] > 0 and zones[1] > 0 and zones[2] > 0


def test_swolf_synthetic() -> None:
    result = chiptime.parse(build_fit.pool_swim())
    per, avg = metrics.swolf(result.activity.sessions[0])
    # 10 real active lengths at 22 strokes/30s + one 0.8s artifact
    assert per[:10] == [52] * 10
    assert avg is not None and 45 < avg < 53


REAL_SWIM = Path(__file__).resolve().parents[2] / "corpus/private/cases/real/pool-swim/input.fit"


@pytest.mark.skipif(not REAL_SWIM.exists(), reason="private tier not on this machine")
def test_swolf_real_pool_swim() -> None:
    result = chiptime.parse(REAL_SWIM.read_bytes())
    per, avg = metrics.swolf(result.activity.sessions[0])
    assert len(per) == 59  # active lengths in the real file
    assert avg is not None and 20 < avg < 80  # physically plausible SWOLF


def test_to_pandas_guarded() -> None:
    result = chiptime.parse(build_fit.ride_smooth())
    records = result.activity.sessions[0].records
    try:
        import pandas  # noqa: F401
    except ImportError:
        with pytest.raises(ImportError, match="chiptime\\[pandas\\]"):
            records.to_pandas()
    else:
        df = records.to_pandas()
        assert len(df) == 120 and "power" in df.columns
