"""Platform validation tests (#99/#102): profiles, repair integration."""

import build_fit

from chiptime.repair import repair
from chiptime.validate import validate


def _codes(findings, level=None):
    return {f.code for f in findings if level is None or f.level == level}


def test_healthy_ride_passes_everywhere() -> None:
    data = build_fit.ride_smooth()
    assert validate(data, "strict-spec") == []
    assert _codes(validate(data, "garmin-connect"), "error") == set()
    assert _codes(validate(data, "strava"), "error") == set()


def test_crash_file_fails_gc_until_repaired() -> None:
    broken = build_fit.no_session()
    errors = _codes(validate(broken, "garmin-connect"), "error")
    assert {"VAL_GC_NO_SESSION", "VAL_GC_NO_ACTIVITY", "VAL_GC_NO_LAP"} <= errors
    # strava is looser: session absence is only a warning (#99)
    assert "VAL_STRAVA_NO_SESSION" in _codes(validate(broken, "strava"), "warning")
    assert _codes(validate(broken, "strava"), "error") == set()

    fixed = repair(broken).data
    assert _codes(validate(fixed, "garmin-connect"), "error") == set()
    assert validate(fixed, "strict-spec") == []


def test_zwift_local_timestamp_gc_rejection_class() -> None:
    data = build_fit.zwift_local1989()
    assert "VAL_GC_LOCAL_TIMESTAMP" in _codes(validate(data, "garmin-connect"), "error")


def test_truncated_file_strict_spec_fails() -> None:
    data = build_fit.ride_smooth()[:-13]
    findings = validate(data, "strict-spec")
    assert findings and findings[0].code == "VAL_SPEC_VIOLATION"


def test_nonmonotonic_warns_gc() -> None:
    data = build_fit.nonmonotonic()
    assert "VAL_GC_NONMONOTONIC_SOURCE" in _codes(validate(data, "garmin-connect"))


def test_cli_validate(tmp_path) -> None:
    from chiptime.cli import main

    p = tmp_path / "a.fit"
    p.write_bytes(build_fit.no_session())
    assert main(["validate", str(p), "--platform", "garmin-connect"]) == 3
    out = tmp_path / "fixed.fit"
    assert main(["repair", str(p), "-o", str(out)]) == 0
    assert main(["validate", str(out), "--platform", "garmin-connect"]) in (0, 2)
