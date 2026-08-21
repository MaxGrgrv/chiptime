"""F28: what a file discloses (`reveal`) and removing it (`scrub`)."""

from __future__ import annotations

from pathlib import Path

import pytest

import chiptime
from chiptime.privacy import COARSE_DECIMALS, ScrubError

REPO = Path(__file__).resolve().parents[2]
CASES = REPO / "corpus" / "cases"
GPS = CASES / "gps" / "spike-bounce" / "input.fit"
RIDE = CASES / "clean" / "ride-smooth" / "input.fit"
REAL_RIDE = REPO / "corpus" / "private" / "cases" / "real" / "wahoo-roam-ride" / "input.fit"
REAL_GARMIN = (
    REPO / "corpus" / "private" / "cases" / "real" / "garmin-format-activity" / "input.fit"
)


def _positions(data: bytes | Path) -> list[tuple[float, float]]:
    parsed = chiptime.parse(data)
    out = []
    for m in parsed.messages:
        lat, lon = m.get("position_lat"), m.get("position_long")
        if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
            out.append((float(lat), float(lon)))
    return out


# --- reveal ---------------------------------------------------------------


def test_reveal_reports_what_is_there_and_what_is_clean() -> None:
    report = chiptime.reveal(GPS)
    assert report.discloses_location
    assert report.positions_present > 0
    # categories genuinely absent are named as clean, not implied to be present
    assert "identity" in report.clean_categories


def test_reveal_coordinates_are_coarse_enough_to_share() -> None:
    """A disclosure report that prints your front door defeats its purpose."""
    report = chiptime.reveal(GPS)
    assert report.start_coarse is not None
    for value in (*report.start_coarse, *(report.end_coarse or ())):
        assert round(value, COARSE_DECIMALS) == value, "coordinates must be rounded"


def test_reveal_writes_nothing_and_is_json_ready() -> None:
    import json

    payload = json.dumps(chiptime.reveal(GPS).to_dict(), sort_keys=True)
    assert '"positions_present"' in payload


# --- scrub: metadata ------------------------------------------------------


def test_scrub_removes_serials_and_output_no_longer_discloses_them() -> None:
    src = REAL_RIDE if REAL_RIDE.exists() else GPS
    before = chiptime.reveal(src)
    result = chiptime.scrub(src)
    assert result.output_strict_ok

    after = chiptime.reveal(result.data)
    assert not [f for f in after.findings if f.category == "serials"], (
        "the scrubbed file must not disclose serials"
    )
    if [f for f in before.findings if f.category == "serials"]:
        assert result.removed.get("serials", 0) > 0
        assert any(p.code == "PII_SERIALS_REMOVED" for p in result.provenance)


@pytest.mark.skipif(not REAL_GARMIN.exists(), reason="private corpus tier not present")
def test_scrub_keeps_workout_measurements_that_share_a_field_name() -> None:
    """`session.max_heart_rate` is the HR reached in the workout — real data.
    Only configured physiology (zones_target/user_profile) is personal."""
    before = chiptime.parse(REAL_GARMIN).activity.sessions[0]
    result = chiptime.scrub(REAL_GARMIN)
    after = chiptime.parse(result.data).activity.sessions[0]
    assert before.declared is not None and after.declared is not None
    assert after.declared.max.get("heart_rate") == before.declared.max.get("heart_rate")
    assert after.derived.distance_m == before.derived.distance_m


def test_scrub_with_everything_disabled_refuses() -> None:
    with pytest.raises(ScrubError) as ei:
        chiptime.scrub(GPS, identity=False, serials=False, body_metrics=False)
    assert ei.value.code == "SCRUB_NOTHING_SELECTED"


def test_scrub_of_a_clean_file_says_so_rather_than_claiming_work() -> None:
    result = chiptime.scrub(RIDE)
    assert result.output_strict_ok
    if not result.removed:
        assert not result.provenance, "no removals means no provenance claims"


# --- scrub: location ------------------------------------------------------


def test_gps_radius_conceals_endpoints_but_keeps_the_middle() -> None:
    src = REAL_RIDE if REAL_RIDE.exists() else GPS
    before = _positions(src)
    if len(before) < 20:
        pytest.skip("fixture has too few positions to distinguish middle from ends")

    result = chiptime.scrub(src, gps_radius_m=300)
    after = _positions(result.data)
    assert result.output_strict_ok
    assert 0 < len(after) < len(before), "some points concealed, but not all"
    assert any(p.code == "PII_LOCATION_CONCEALED" for p in result.provenance)

    # the surviving points are all far from the original endpoints
    from chiptime.privacy import _haversine_m

    for point in after:
        assert min(_haversine_m(point, before[0]), _haversine_m(point, before[-1])) > 300


def test_concealed_positions_decode_as_absent_never_zero() -> None:
    """Null Island is a real place; 'no reading' must not become 0,0."""
    result = chiptime.scrub(GPS, drop_all_gps=True)
    parsed = chiptime.parse(result.data, mode="strict")
    for m in parsed.messages:
        for fname in ("position_lat", "position_long"):
            if fname in m.fields:
                assert m.fields[fname].value is None, f"{fname} leaked a value"
    assert not _positions(result.data)


def test_location_scrub_leaves_totals_untouched() -> None:
    src = REAL_GARMIN if REAL_GARMIN.exists() else GPS
    before = chiptime.parse(src).activity.sessions[0]
    result = chiptime.scrub(src, gps_radius_m=500)
    after = chiptime.parse(result.data).activity.sessions[0]
    assert after.derived.distance_m == before.derived.distance_m
    assert after.derived.elapsed_time_s == before.derived.elapsed_time_s


def test_concealing_everything_warns() -> None:
    result = chiptime.scrub(GPS, gps_radius_m=100_000_000)  # radius swallows the planet
    assert any(w.code == "SCRUB_ALL_POSITIONS_CONCEALED" for w in result.warnings)


def test_scrub_is_deterministic() -> None:
    a = chiptime.scrub(GPS, gps_radius_m=200).data
    b = chiptime.scrub(GPS, gps_radius_m=200).data
    assert a == b


def test_scrubbed_file_still_passes_platform_validation() -> None:
    from chiptime.validate import validate

    src_errors = [f for f in validate(GPS, platform="garmin-connect") if f.level == "error"]
    result = chiptime.scrub(GPS, gps_radius_m=200)
    out = REPO / "python" / ".pytest-scrub-tmp.fit"
    try:
        out.write_bytes(result.data)
        after = [f for f in validate(out, platform="garmin-connect") if f.level == "error"]
        assert len(after) <= len(src_errors)
    finally:
        out.unlink(missing_ok=True)


# --- CLI ------------------------------------------------------------------


def test_cli_reveal_and_scrub(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from chiptime.cli import main

    assert main(["reveal", str(GPS)]) == 0
    assert "discloses" in capsys.readouterr().out

    dest = tmp_path / "clean.fit"
    assert main(["scrub", str(GPS), "-o", str(dest), "--gps-radius", "200"]) == 0
    assert "wrote" in capsys.readouterr().out
    assert dest.exists()

    assert main(["reveal", str(dest), "--json"]) == 0
    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["positions_present"] < chiptime.reveal(GPS).positions_present
