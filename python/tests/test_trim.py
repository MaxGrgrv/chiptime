"""F27: crop an activity and rebuild every number that depended on it."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

import chiptime
from chiptime.trim import TrimError

REPO = Path(__file__).resolve().parents[2]
CASES = REPO / "corpus" / "cases"
RIDE = CASES / "clean" / "ride-smooth" / "input.fit"
TRI = CASES / "multisport" / "triathlon" / "input.fit"
SWIM_LENGTHS_ONLY = CASES / "swim" / "pool-lengths" / "input.fit"
REAL_SWIM = REPO / "corpus" / "private" / "cases" / "real" / "pool-swim" / "input.fit"


def _session(result_or_path: Any) -> Any:
    parsed = (
        chiptime.parse(result_or_path)
        if isinstance(result_or_path, (str, Path))
        else chiptime.parse(result_or_path.data)
    )
    return parsed.activity.sessions[0]


def _records(data: bytes, gnum: int = 20) -> int:
    return sum(1 for m in chiptime.parse(data).messages if m.global_num == gnum)


# --- the core promise: the trimmed file must not lie -----------------------


def test_trimmed_totals_are_rebuilt_not_carried_over() -> None:
    before = _session(RIDE)
    result = chiptime.trim(RIDE, after="+30s", before="-30s")
    assert result.output_strict_ok

    after = _session(result)
    assert after.records.n == result.records_kept < before.records.n
    # the declared summary in the output must equal what its own records prove
    assert after.declared is not None
    assert after.declared.distance_m == pytest.approx(after.derived.distance_m)
    assert after.declared.elapsed_time_s == pytest.approx(after.derived.elapsed_time_s)
    # and it must actually differ from the untrimmed totals (a real trim happened)
    assert after.derived.distance_m < before.derived.distance_m
    assert {p.code for p in result.provenance} >= {
        "TRIM_RECORDS_DROPPED",
        "TRIM_SUMMARIES_REBUILT",
    }


def test_relative_and_absolute_bounds_agree() -> None:
    """'+30s' must select the same window as the absolute datetime it means."""
    start = _session(RIDE).records.time[0]
    relative = chiptime.trim(RIDE, after="+30s")
    absolute = chiptime.trim(RIDE, after=start + timedelta(seconds=30))
    assert relative.records_kept == absolute.records_kept
    assert relative.data == absolute.data


def test_trim_is_deterministic() -> None:
    a = chiptime.trim(RIDE, after="+10s", before="-10s").data
    b = chiptime.trim(RIDE, after="+10s", before="-10s").data
    assert a == b


# --- structure preservation ------------------------------------------------


def test_laps_wholly_inside_survive_and_straddlers_are_reported() -> None:
    before_laps = [m for m in chiptime.parse(TRI).messages if m.global_num == 19]
    assert len(before_laps) >= 2, "fixture must have laps to exercise this"

    result = chiptime.trim(TRI, before="-10s")  # clip the tail: last lap straddles
    assert result.output_strict_ok
    dropped = [p for p in result.provenance if p.code == "TRIM_LAP_DROPPED"]
    assert dropped, "a straddling lap must be reported, never silently removed"
    assert dropped[0].data["lap_message_indices"]

    kept_laps = [m for m in chiptime.parse(result.data).messages if m.global_num == 19]
    assert len(kept_laps) < len(before_laps), "the straddling lap is gone"
    assert kept_laps, "laps wholly inside the window must survive unchanged"


def test_in_window_events_are_preserved() -> None:
    """Dropping every event would erase pause structure and inflate moving
    time — the critique's second required change."""
    before = [m for m in chiptime.parse(RIDE).messages if m.global_num == 21]
    result = chiptime.trim(RIDE, after="+1s")
    after = [m for m in chiptime.parse(result.data).messages if m.global_num == 21]
    assert after, "the output must carry timer events"
    if before:
        kept_ts = {m.get_raw("timestamp") for m in after}
        assert kept_ts, "surviving events keep their own timestamps"


@pytest.mark.skipif(not REAL_SWIM.exists(), reason="private corpus tier not present")
def test_pool_lengths_outside_the_window_are_dropped() -> None:
    result = chiptime.trim(REAL_SWIM, after="+5m")
    assert result.output_strict_ok
    entry = next(p for p in result.provenance if p.code == "TRIM_RECORDS_DROPPED")
    assert entry.data["lengths_dropped"] > 0
    assert _records(result.data, 101) > 0, "in-window lengths must survive"
    after = _session(result)
    assert after.declared.distance_m == pytest.approx(after.derived.distance_m)


# --- refusals --------------------------------------------------------------


def test_empty_window_refuses_and_writes_nothing() -> None:
    with pytest.raises(TrimError) as ei:
        chiptime.trim(RIDE, after="-1s", before="+1s")  # inverted window
    assert ei.value.code == "TRIM_EMPTY_RESULT"
    assert ei.value.suggestion


def test_no_window_is_an_error() -> None:
    with pytest.raises(TrimError) as ei:
        chiptime.trim(RIDE)
    assert ei.value.code == "TRIM_NO_WINDOW"


def test_unparseable_bound_is_reported_clearly() -> None:
    with pytest.raises(TrimError) as ei:
        chiptime.trim(RIDE, after="next tuesday")
    assert ei.value.code == "TRIM_BAD_BOUND"


def test_length_only_file_refuses_honestly() -> None:
    """Totals could not be rebuilt from lengths alone, so chiptime says so
    rather than carrying a stale summary forward."""
    with pytest.raises(TrimError) as ei:
        chiptime.trim(SWIM_LENGTHS_ONLY, after="+10s")
    assert ei.value.code == "TRIM_NO_RECORDS"
    assert "not trimmable yet" in ei.value.detail


# --- platform acceptance + CLI ---------------------------------------------


def test_trimmed_file_still_passes_platform_validation() -> None:
    from chiptime.validate import validate

    src_errors = [f for f in validate(RIDE, platform="garmin-connect") if f.level == "error"]
    result = chiptime.trim(RIDE, after="+10s")
    out = REPO / "python" / ".pytest-trim-tmp.fit"
    try:
        out.write_bytes(result.data)
        after_errors = [f for f in validate(out, platform="garmin-connect") if f.level == "error"]
        assert len(after_errors) <= len(src_errors)
    finally:
        out.unlink(missing_ok=True)


def test_cli_trim(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from chiptime.cli import main

    dest = tmp_path / "trimmed.fit"
    assert main(["trim", str(RIDE), "-o", str(dest), "--after", "+30s"]) == 0
    out = capsys.readouterr().out
    assert "TRIM_RECORDS_DROPPED" in out and "records kept" in out
    assert _records(dest.read_bytes()) < _records(RIDE.read_bytes())


def test_cli_trim_without_bounds_is_usage_error(tmp_path: Path) -> None:
    from chiptime.cli import main

    assert main(["trim", str(RIDE), "-o", str(tmp_path / "x.fit")]) == 64
