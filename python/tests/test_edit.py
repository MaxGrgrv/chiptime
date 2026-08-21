"""F26: user-directed metadata edits with a validated round-trip."""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path
from typing import Any

import pytest

import chiptime
from chiptime.edit import TS_MAX, EditError

REPO = Path(__file__).resolve().parents[2]
CASES = REPO / "corpus" / "cases"
RIDE = CASES / "clean" / "ride-smooth" / "input.fit"
TRI = CASES / "multisport" / "triathlon" / "input.fit"
ZWIFT = CASES / "temporal" / "zwift-local-timestamp-1989" / "input.fit"
UNKNOWN = CASES / "protocol" / "unknown-enum-values" / "input.fit"
STRYD = CASES / "devfields" / "stryd-known-vendor" / "input.fit"


def _changed_fields(before: Any, after: Any) -> set[tuple[int, str, str]]:
    """(index, message, field) for every field whose value differs."""
    out: set[tuple[int, str, str]] = set()
    assert len(before.messages) == len(after.messages), "message count must not change"
    for i, (a, b) in enumerate(zip(before.messages, after.messages, strict=True)):
        assert a.name == b.name
        assert set(a.fields) == set(b.fields), f"field set changed in {a.name}"
        for fname, fv in a.fields.items():
            if b.fields[fname].value != fv.value:
                out.add((i, a.name, fname))
    return out


# --- sport ---------------------------------------------------------------


def test_sport_edit_applies_everywhere_sport_is_declared() -> None:
    before = chiptime.parse(TRI)
    result = chiptime.edit(TRI, sport="running")
    assert result.output_strict_ok
    after = chiptime.parse(result.data)

    changed = _changed_fields(before, after)
    assert changed, "the edit must actually change something"
    assert {f for _, _, f in changed} == {"sport"}, "only sport may change"
    # every session that declared a sport now declares running — no contradictions
    sports = {m.get("sport") for m in after.messages if "sport" in m.fields}
    assert sports == {"running"}
    assert all(p.code == "SPORT_EDITED" for p in result.provenance)
    assert result.provenance[0].data["after"] == "running"


def test_sport_edit_accepts_raw_numbers_and_rejects_nonsense() -> None:
    result = chiptime.edit(TRI, sport=1)  # 1 == running
    after = chiptime.parse(result.data)
    assert {m.get("sport") for m in after.messages if "sport" in m.fields} == {"running"}
    with pytest.raises(EditError) as ei:
        chiptime.edit(TRI, sport="quidditch")
    assert ei.value.code == "UNKNOWN_ENUM_NAME"
    assert ei.value.suggestion


def test_changing_sport_warns_when_a_real_sub_sport_is_left_behind() -> None:
    result = chiptime.edit(TRI, sport="running")
    assert any(w.code == "SPORT_PAIR_IMPLAUSIBLE" for w in result.warnings)
    # naming the sub_sport silences the warning — chiptime never guesses it
    both = chiptime.edit(TRI, sport="running", sub_sport="generic")
    assert not both.warnings
    after = chiptime.parse(both.data)
    assert {m.get("sub_sport") for m in after.messages if "sub_sport" in m.fields} == {"generic"}


# --- device --------------------------------------------------------------


def test_device_edit_rewrites_creator_identity_only() -> None:
    before = chiptime.parse(RIDE)
    result = chiptime.edit(RIDE, manufacturer="garmin", product=2480)
    assert result.output_strict_ok
    after = chiptime.parse(result.data)

    assert {f for _, _, f in _changed_fields(before, after)} <= {"manufacturer", "product"}
    file_id = next(m for m in after.messages if m.name == "file_id")
    assert file_id.get("manufacturer") == "garmin"
    assert file_id.get("product") == 2480
    assert {p.code for p in result.provenance} == {"DEVICE_EDITED"}


def test_device_edit_requires_numeric_product() -> None:
    with pytest.raises(EditError) as ei:
        chiptime.edit(RIDE, product="edge_1030")  # type: ignore[arg-type]
    assert ei.value.code == "UNKNOWN_ENUM_NAME"


# --- time shift ----------------------------------------------------------


def test_time_shift_preserves_spacing_and_the_local_utc_pair() -> None:
    before = chiptime.parse(ZWIFT)
    shift = 3 * 3600
    result = chiptime.edit(ZWIFT, time_shift_s=shift)
    assert result.output_strict_ok
    after = chiptime.parse(result.data)

    def stamps(res: Any) -> list[int]:
        return [m.get_raw("timestamp") for m in res.messages if m.get_raw("timestamp") is not None]

    a, b = stamps(before), stamps(after)
    assert b == [t + shift for t in a], "every timestamp moves by exactly the offset"
    gaps_before = [y - x for x, y in pairwise(a)]
    gaps_after = [y - x for x, y in pairwise(b)]
    assert gaps_before == gaps_after, "relative spacing must be preserved"

    # the local/UTC pair keeps its offset: both sides shifted equally (#37/#47)
    def pair(res: Any) -> tuple[int, int] | None:
        for m in res.messages:
            if m.get_raw("local_timestamp") is not None and m.get_raw("timestamp") is not None:
                return m.get_raw("timestamp"), m.get_raw("local_timestamp")
        return None

    p_before, p_after = pair(before), pair(after)
    if p_before is not None:
        assert p_after is not None
        assert p_after[0] - p_after[1] == p_before[0] - p_before[1]

    prov = result.provenance[0]
    assert prov.code == "TIMESTAMPS_SHIFTED"
    assert prov.data["seconds"] == shift and prov.data["fields_shifted"] > 0


def test_time_shift_refuses_to_leave_the_representable_range() -> None:
    with pytest.raises(EditError) as ei:
        chiptime.edit(RIDE, time_shift_s=TS_MAX)  # would overflow, and onto the sentinel
    assert ei.value.code == "TIME_SHIFT_OUT_OF_RANGE"
    with pytest.raises(EditError):
        chiptime.edit(RIDE, time_shift_s=-(TS_MAX))  # underflow below the FIT epoch


# --- preservation --------------------------------------------------------


def test_unrelated_content_survives_an_edit() -> None:
    """Unknown enums, unknown fields, and developer fields must not be
    collateral damage of an unrelated edit (contracts #1 and #6)."""
    for src, kwargs in ((UNKNOWN, {"time_shift_s": 60}), (STRYD, {"sport": "running"})):
        before = chiptime.parse(src)
        result = chiptime.edit(src, **kwargs)  # type: ignore[arg-type]
        after = chiptime.parse(result.data)
        changed = _changed_fields(before, after)
        allowed = {"timestamp", "local_timestamp", "start_time", "time_created", "sport"}
        assert {f for _, _, f in changed} <= allowed, f"collateral change in {src.name}"

    # unknown enum values specifically stay raw numbers, never nulled
    edited = chiptime.parse(chiptime.edit(UNKNOWN, time_shift_s=60).data)
    file_id = next(m for m in edited.messages if m.name == "file_id")
    assert file_id.get("manufacturer") == 64999
    session = next(m for m in edited.messages if m.name == "session")
    assert session.get("sport") == 250 and session.get("sub_sport") == 240

    # developer fields survive with their vendor naming intact
    stryd = chiptime.parse(chiptime.edit(STRYD, sport="running").data)
    dev_named = [
        name for m in stryd.messages for name, fv in m.fields.items() if fv.developer is not None
    ]
    assert dev_named, "developer fields must survive an unrelated edit"


# --- policy --------------------------------------------------------------


def test_edit_without_an_edit_is_an_error() -> None:
    with pytest.raises(EditError) as ei:
        chiptime.edit(RIDE)
    assert ei.value.code == "NO_EDIT_REQUESTED"


def test_edited_file_still_passes_platform_validation() -> None:
    from chiptime.validate import validate

    src_findings = [f for f in validate(RIDE, platform="garmin-connect") if f.level == "error"]
    result = chiptime.edit(RIDE, sport="running")
    out = REPO / "python" / ".pytest-edit-tmp.fit"
    try:
        out.write_bytes(result.data)
        after = [f for f in validate(out, platform="garmin-connect") if f.level == "error"]
        assert len(after) <= len(src_findings), "an edit must not break platform acceptance"
    finally:
        out.unlink(missing_ok=True)


def test_cli_edit_roundtrip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from chiptime.cli import main

    dest = tmp_path / "edited.fit"
    code = main(
        ["edit", str(RIDE), "-o", str(dest), "--sport", "running", "--time-shift", "+01:30"]
    )
    assert code == 0
    assert dest.exists()
    out = capsys.readouterr().out
    assert "SPORT_EDITED" in out and "TIMESTAMPS_SHIFTED" in out

    reparsed = chiptime.parse(dest, mode="strict")
    assert {m.get("sport") for m in reparsed.messages if "sport" in m.fields} == {"running"}
    original = chiptime.parse(RIDE)
    a = next(m.get_raw("timestamp") for m in original.messages if m.get_raw("timestamp"))
    b = next(m.get_raw("timestamp") for m in reparsed.messages if m.get_raw("timestamp"))
    assert b - a == 5400  # +01:30 parsed as 5,400 seconds


def test_cli_edit_without_changes_is_usage_error(tmp_path: Path) -> None:
    from chiptime.cli import main

    assert main(["edit", str(RIDE), "-o", str(tmp_path / "x.fit")]) == 64
