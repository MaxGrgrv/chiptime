"""CLI tests: exit codes, JSON/summary output, inspect, codes registry."""

import sys

import build_fit
import corrupt
import pytest

from chiptime.cli import main


@pytest.fixture
def fit_file(tmp_path):
    p = tmp_path / "ride.fit"
    p.write_bytes(build_fit.ride_smooth())
    return str(p)


def test_parse_clean_exit_0(fit_file, capsys) -> None:
    assert main(["parse", fit_file]) == 0
    out = capsys.readouterr().out
    assert "session[0] cycling" in out and "records=120" in out


def test_parse_json_canonical(fit_file, capsys) -> None:
    assert main(["parse", fit_file, "--json"]) == 0
    out = capsys.readouterr().out
    assert out.startswith('{"chiptime_schema":1')


def test_truncated_exit_2(tmp_path, capsys) -> None:
    p = tmp_path / "cut.fit"
    p.write_bytes(build_fit.ride_smooth()[:-13])
    assert main(["parse", str(p)]) == 2
    assert "TRUNCATED_TAIL_SALVAGED" in capsys.readouterr().out


def test_not_fit_exit_4(tmp_path, capsys) -> None:
    p = tmp_path / "fake.fit"
    p.write_bytes(corrupt.payload("gpx"))
    assert main(["parse", str(p)]) == 4
    assert "GPX" in capsys.readouterr().out


def test_strict_not_fit_exit_4(tmp_path) -> None:
    p = tmp_path / "fake.fit"
    p.write_bytes(corrupt.payload("html"))
    assert main(["parse", str(p), "--mode", "strict"]) == 4


def test_empty_exit_3(tmp_path) -> None:
    p = tmp_path / "empty.fit"
    p.write_bytes(b"")
    assert main(["parse", str(p)]) == 3


def test_output_file(fit_file, tmp_path) -> None:
    out = tmp_path / "out.json"
    assert main(["parse", fit_file, "-o", str(out)]) == 0
    assert out.read_bytes().startswith(b'{"chiptime_schema":1')


def test_inspect(fit_file, capsys) -> None:
    assert main(["inspect", fit_file, "--limit", "10"]) == 0
    out = capsys.readouterr().out
    assert "header" in out and "define" in out and "data" in out


def test_codes(capsys) -> None:
    assert main(["codes"]) == 0
    out = capsys.readouterr().out
    assert "FIT_TRUNCATED" in out and "SESSION_REBUILT" in out


def test_usage_error_64(capsys) -> None:
    with pytest.raises(SystemExit) as ei:
        main(["parse"])  # missing file
    assert ei.value.code == 64


def test_module_entry_point(fit_file) -> None:
    import subprocess

    r = subprocess.run(
        [sys.executable, "-m", "chiptime", "parse", fit_file, "--json"],
        capture_output=True,
    )
    assert r.returncode == 0
    assert r.stdout.startswith(b'{"chiptime_schema":1')
