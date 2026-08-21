"""F29: doctor (why won't this upload) + distance calibration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import chiptime
from chiptime.validate import validate

REPO = Path(__file__).resolve().parents[2]
CASES = REPO / "corpus" / "cases"
BROKEN = CASES / "reconcile" / "no-session-rebuild" / "input.fit"
TRUNCATED = CASES / "structural" / "truncated-mid-record" / "input.fit"
CLEAN = CASES / "clean" / "ride-smooth" / "input.fit"
RUN = CASES / "clean" / "run-basic" / "input.fit"
NO_STOP = CASES / "temporal" / "missing-final-stop" / "input.fit"


# --- the promise: prescribe, run it, and the file uploads -----------------


@pytest.mark.parametrize("src", [BROKEN, TRUNCATED, NO_STOP], ids=lambda p: p.parent.name)
def test_prescription_actually_works(src: Path, tmp_path: Path) -> None:
    """A remedy that doesn't work is worse than no remedy, so the advice is
    executed end-to-end here rather than merely asserted."""
    before = chiptime.doctor(src)
    assert not before.will_upload, "fixture must start rejected"
    assert before.remedies, "a rejected file must come with a prescription"
    assert any("repair" in r.command for r in before.remedies)

    fixed = tmp_path / "fixed.fit"
    fixed.write_bytes(chiptime.repair(src).data)

    after = chiptime.doctor(fixed)
    assert after.will_upload, f"after the prescribed fix: {[f.code for f in after.blocking]}"
    assert not after.blocking


def test_clean_file_is_reported_clean_with_no_advice() -> None:
    diagnosis = chiptime.doctor(CLEAN)
    assert diagnosis.will_upload
    assert not diagnosis.blocking
    assert not diagnosis.remedies, "don't prescribe anything for a healthy file"


def test_remedies_are_deduplicated_and_ordered() -> None:
    diagnosis = chiptime.doctor(BROKEN)
    commands = [r.command for r in diagnosis.remedies]
    assert len(commands) == len(set(commands)), "one repair, not one per finding"
    assert diagnosis.remedies[0].priority <= diagnosis.remedies[-1].priority
    # the single repair remedy claims every code it resolves
    repair = next(r for r in diagnosis.remedies if "repair" in r.command)
    assert len(repair.codes) >= 3


def test_unresolved_findings_are_named_not_papered_over() -> None:
    diagnosis = chiptime.doctor(BROKEN)
    covered = {c for r in diagnosis.remedies for c in r.codes}
    for finding in diagnosis.blocking:
        assert finding.code in covered or finding in diagnosis.unresolved


def test_summary_reports_the_parse_itself() -> None:
    assert "records" in chiptime.doctor(CLEAN).summary


def test_json_output_is_deterministic() -> None:
    a = json.dumps(chiptime.doctor(BROKEN).to_dict(), sort_keys=True)
    b = json.dumps(chiptime.doctor(BROKEN).to_dict(), sort_keys=True)
    assert a == b
    assert json.loads(a)["will_upload"] is False


# --- validator addition ---------------------------------------------------


def test_missing_timer_stop_is_a_warning_not_a_rejection() -> None:
    """The rule is community-observed, not documented — so it must never
    manufacture a rejection for a file the platform would accept."""
    findings = validate(NO_STOP, platform="garmin-connect")
    stop = [f for f in findings if f.code == "VAL_GC_NO_TIMER_STOP"]
    assert stop and stop[0].level == "warning"
    assert "reported" in stop[0].detail
    assert not validate(CLEAN, platform="garmin-connect")


# --- distance calibration -------------------------------------------------


def test_distance_calibration_keeps_the_file_self_consistent() -> None:
    before = chiptime.parse(RUN).activity.sessions[0]
    recorded = before.derived.distance_m
    assert recorded
    target = recorded * 1.05

    result = chiptime.edit(RUN, total_distance_m=target)
    assert result.output_strict_ok
    after = chiptime.parse(result.data).activity.sessions[0]

    assert after.derived.distance_m == pytest.approx(target, rel=0.01)
    # speed must scale by the same factor, or the stream contradicts the total
    assert after.derived.avg["speed"] == pytest.approx(before.derived.avg["speed"] * 1.05, rel=0.01)
    entry = next(p for p in result.provenance if p.code == "DISTANCE_RESCALED")
    assert entry.data["factor"] == pytest.approx(1.05, rel=0.01)


def test_absurd_calibration_refuses_rather_than_overflow() -> None:
    with pytest.raises(chiptime.FitError) as ei:
        chiptime.edit(RUN, total_distance_m=5_000.0)  # ~28x the recorded distance
    assert ei.value.code == "DISTANCE_SCALE_OUT_OF_RANGE"
    assert "no bytes were written" in (ei.value.suggestion or "")


def test_calibration_falls_back_to_the_declared_total() -> None:
    """A length-only swim has no record distance stream but does declare a
    total; rescaling from the declared figure is the sensible reading."""
    swim = CASES / "swim" / "pool-lengths" / "input.fit"
    declared = chiptime.parse(swim).activity.sessions[0].declared
    assert declared is not None and declared.distance_m
    result = chiptime.edit(swim, total_distance_m=declared.distance_m * 1.1)
    entry = next(p for p in result.provenance if p.code == "DISTANCE_RESCALED")
    assert entry.data["from_m"] == pytest.approx(declared.distance_m)
    assert result.output_strict_ok


# --- CLI ------------------------------------------------------------------


def test_cli_doctor_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from chiptime.cli import main

    assert main(["doctor", str(BROKEN)]) == 2, "fixable → exit 2"
    out = capsys.readouterr().out
    assert "blocking" in out and "chiptime repair" in out

    assert main(["doctor", str(CLEAN)]) == 0, "clean → exit 0"
    assert "should upload" in capsys.readouterr().out

    fixed = tmp_path / "fixed.fit"
    fixed.write_bytes(chiptime.repair(BROKEN).data)
    assert main(["doctor", str(fixed), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["will_upload"] is True


def test_cli_edit_total_distance(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from chiptime.cli import main

    dest = tmp_path / "calibrated.fit"
    recorded = chiptime.parse(RUN).activity.sessions[0].derived.distance_m
    assert recorded
    code = main(
        ["edit", str(RUN), "-o", str(dest), "--total-distance", str(round(recorded * 1.02, 1))]
    )
    assert code == 0
    assert "DISTANCE_RESCALED" in capsys.readouterr().out
