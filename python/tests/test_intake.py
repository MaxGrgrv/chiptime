"""Intake tests: containers, sniffing, chaining, trailing junk, routing."""

import build_fit
import corrupt
import pytest

import chiptime
from chiptime.errors import NotFitError, ProtocolError


def test_gzip_wrapped() -> None:
    result = chiptime.parse(corrupt.gzip_wrap(build_fit.ride_smooth()))
    assert result.ok and result.source.unwrapped == ("gzip",)
    assert len([m for m in result.messages if m.name == "record"]) == 120


def test_zip_wrapped() -> None:
    result = chiptime.parse(corrupt.zip_wrap(build_fit.ride_smooth(), name="ride.fit"))
    assert result.ok and result.source.unwrapped == ("zip",)


def test_zip_multiple_entries_chain() -> None:
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for i, blob in enumerate([build_fit.ride_smooth(), build_fit.run_basic()]):
            info = zipfile.ZipInfo(f"a{i}.fit", date_time=(1980, 1, 1, 0, 0, 0))
            z.writestr(info, blob)
    result = chiptime.parse(buf.getvalue())
    assert result.ok and len(result.parts) == 2
    assert any(p.code == "ZIP_ENTRIES_CHAINED" for p in result.provenance)


def test_nested_gzip_of_zip() -> None:
    inner = corrupt.zip_wrap(build_fit.run_basic())
    result = chiptime.parse(corrupt.gzip_wrap(inner))
    assert result.ok and result.source.unwrapped == ("gzip", "zip")


@pytest.mark.parametrize(
    ("kind", "expect_in_detail"),
    [("gpx", "GPX"), ("tcx", "TCX"), ("html", "HTML"), ("json", "JSON")],
)
def test_not_fit_sniffing(kind: str, expect_in_detail: str) -> None:
    data = corrupt.payload(kind)
    result = chiptime.parse(data)
    assert not result.ok
    assert result.errors[0].code == "NOT_FIT_FORMAT"
    assert expect_in_detail in result.errors[0].detail
    with pytest.raises(NotFitError):
        chiptime.parse(data, mode="strict")


def test_chained_files() -> None:
    data = corrupt.chain(build_fit.ride_smooth(), seeds=[build_fit.run_basic()])
    result = chiptime.parse(data)
    assert result.ok and len(result.parts) == 2
    assert [p.file_type for p in result.parts] == ["activity", "activity"]


def test_trailing_junk() -> None:
    data = corrupt.append(build_fit.run_basic(), repeat_byte=0xAB, count=57)
    result = chiptime.parse(data)
    assert result.ok
    assert any(w.code == "FIT_TRAILING_JUNK" for w in result.warnings)
    with pytest.raises(ProtocolError) as ei:
        chiptime.parse(data, mode="strict")
    assert ei.value.code == "FIT_TRAILING_JUNK"


def test_routing_file_types() -> None:
    assert chiptime.parse(build_fit.course_file()).file_type == "course"
    assert chiptime.parse(build_fit.workout_file()).file_type == "workout"
    assert chiptime.parse(build_fit.monitoring_file()).file_type == "monitoring_a"


def test_summary_only_activity_is_valid() -> None:
    result = chiptime.parse(build_fit.summary_only())
    assert result.ok and not result.errors
    assert not [m for m in result.messages if m.name == "record"]
    assert [m for m in result.messages if m.name == "session"]
