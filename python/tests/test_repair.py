"""Repair pipeline tests: salvage→synthesize→valid file; honest refusal."""

import build_fit
import pytest

import chiptime
from chiptime.repair import NotRepairableError, repair


def test_repair_truncated_ride() -> None:
    broken = build_fit.ride_smooth()[:-13]  # the cut clips the trailing activity msg
    rr = repair(broken)
    assert rr.output_strict_ok
    assert any(p.code == "REPAIR_ACTIVITY_SYNTHESIZED" for p in rr.provenance)
    fixed = chiptime.parse(rr.data, mode="strict")
    assert fixed.ok and not fixed.errors
    s = fixed.activity.sessions[0]
    assert s.records.n == 120  # every record salvaged into the repaired file
    assert not s.rebuilt  # original session message preserved
    assert [m.name for m in fixed.messages].count("session") == 1
    assert [m.name for m in fixed.messages].count("activity") == 1


def test_repair_deep_truncation_rebuilds_session() -> None:
    broken = build_fit.ride_smooth()[:2000]  # cut deep inside the record stream
    rr = repair(broken)
    codes = {p.code for p in rr.provenance}
    assert "REPAIR_SESSION_SYNTHESIZED" in codes  # session msg was lost with the tail
    fixed = chiptime.parse(rr.data, mode="strict")
    assert fixed.ok
    s = fixed.activity.sessions[0]
    assert 0 < s.records.n < 120
    assert s.declared is not None and s.declared.elapsed_time_s is not None


def test_repair_zwift_crash_class() -> None:
    rr = repair(build_fit.no_session())  # records+events, no summaries (#95)
    codes = {p.code for p in rr.provenance}
    assert "REPAIR_SESSION_SYNTHESIZED" in codes
    assert "REPAIR_LAP_SYNTHESIZED" in codes
    assert "REPAIR_ACTIVITY_SYNTHESIZED" in codes
    assert "REPAIR_EVENTS_SYNTHESIZED" not in codes  # events existed
    fixed = chiptime.parse(rr.data, mode="strict")
    assert fixed.ok
    s = fixed.activity.sessions[0]
    assert s.declared is not None  # summary now DECLARED in-file
    assert s.declared.elapsed_time_s == 89.0
    assert s.sport == "cycling"
    assert s.declared.avg["heart_rate"] == 145
    # platform minimum structure (#102): file_id, events, lap, session, activity
    names = {m.name for m in fixed.messages}
    assert {"file_id", "event", "lap", "session", "activity"} <= names


def test_repair_preserves_original_summaries() -> None:
    rr = repair(build_fit.ride_smooth())
    codes = {p.code for p in rr.provenance}
    assert codes == {"REPAIR_REENCODED"}  # nothing synthesized on a healthy file
    assert rr.output_strict_ok


def test_repair_refuses_fabrication() -> None:
    b = build_fit.FitBuilder()
    b.define(0, build_fit.FILE_ID, [(0, "enum", 1)])
    b.data(0, 4)  # structurally fine, genuinely empty (#16 class)
    with pytest.raises(NotRepairableError) as ei:
        repair(b.build())
    assert ei.value.code == "REPAIR_NOTHING_TO_SALVAGE"


def test_repair_deterministic() -> None:
    broken = build_fit.ride_smooth()[:-13]
    assert repair(broken).data == repair(broken).data


def test_repair_cli(tmp_path) -> None:
    from chiptime.cli import main

    src = tmp_path / "broken.fit"
    src.write_bytes(build_fit.no_session())
    out = tmp_path / "fixed.fit"
    assert main(["repair", str(src), "-o", str(out)]) == 0
    assert chiptime.parse(out.read_bytes(), mode="strict").ok


def test_repair_cli_refusal(tmp_path, capsys) -> None:
    from chiptime.cli import main

    src = tmp_path / "empty.fit"
    src.write_bytes(b"")
    assert main(["repair", str(src), "-o", str(tmp_path / "x.fit")]) == 3


def test_repair_drops_zwift_local_timestamp() -> None:
    """F17: repaired files must clear the GC local_timestamp rejection (#37)."""
    from chiptime.validate import validate

    rr = repair(build_fit.zwift_local1989())
    assert any(p.code == "REPAIR_LOCAL_TIMESTAMP_DROPPED" for p in rr.provenance)
    findings = validate(rr.data, "garmin-connect")
    assert not any(f.code == "VAL_GC_LOCAL_TIMESTAMP" for f in findings)
    fixed = chiptime.parse(rr.data)
    assert not any(w.code == "LOCAL_TIMESTAMP_IMPLAUSIBLE" for w in fixed.warnings)
