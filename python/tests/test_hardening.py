"""M1 hardening gates: cross-process determinism and the truncation sweep.

Contract #2 (byte-identical across processes) and the fuzz-lite guarantee:
truncating a valid file at EVERY byte offset must never raise in lenient
mode, never hang, and always yield serializable canonical output.
"""

import contextlib
import subprocess
import sys

import build_fit

import chiptime


def test_determinism_across_processes(tmp_path) -> None:
    data = build_fit.ride_smooth()
    src = tmp_path / "ride.fit"
    src.write_bytes(data)
    outs = []
    for _ in range(2):
        r = subprocess.run(
            [sys.executable, "-m", "chiptime", "parse", str(src), "--json"],
            capture_output=True,
            check=True,
        )
        outs.append(r.stdout)
    assert outs[0] == outs[1]
    assert outs[0].rstrip(b"\n") == chiptime.parse(data).to_canonical_json()


def test_truncation_sweep_never_raises() -> None:
    data = build_fit.run_basic()
    for cut in range(len(data)):
        result = chiptime.parse(data[:cut])  # must never raise (lenient)
        result.to_canonical_json()  # must always serialize


def test_truncation_sweep_strict_always_raises_or_parses() -> None:
    data = build_fit.compressed_ts()
    for cut in range(len(data)):
        with contextlib.suppress(chiptime.FitError):
            # a typed FitError is the strict contract; anything else fails the test
            chiptime.parse(data[:cut], mode="strict")


def test_crc256_equals_nibble_algorithm() -> None:
    """F20: the byte-wise CRC table must equal the FIT nibble algorithm."""
    from chiptime.frames import CRC_TABLE, crc16

    def nibble(data: bytes, crc: int = 0) -> int:
        for byte in data:
            tmp = CRC_TABLE[crc & 0xF]
            crc = (crc >> 4) & 0x0FFF
            crc = crc ^ tmp ^ CRC_TABLE[byte & 0xF]
            tmp = CRC_TABLE[crc & 0xF]
            crc = (crc >> 4) & 0x0FFF
            crc = crc ^ tmp ^ CRC_TABLE[(byte >> 4) & 0xF]
        return crc

    payloads = [b"", b"\x00", b"\xff" * 33, bytes(range(256)) * 5, build_fit.ride_smooth()]
    for p in payloads:
        assert crc16(p) == nibble(p)


def test_fast_iso_equals_strftime() -> None:
    """F20: the civil-from-days formatter must equal datetime across eras."""
    from datetime import UTC, datetime

    from chiptime.decode import FIT_EPOCH_UNIX, fit_ts_to_iso

    samples = [0, 1, 86399, 86400, 631238400, 1149238800, 2**31 - 1, 959_000_000, 1_100_000_000]
    for fs in samples:
        want = datetime.fromtimestamp(FIT_EPOCH_UNIX + fs, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        assert fit_ts_to_iso(fs) == want, fs


def test_bitflip_sweep_never_raises() -> None:
    """Pre-M3 gate: one flipped bit at EVERY byte offset must never crash
    lenient parsing nor break canonical serialization (taxonomy #17 en masse).
    A second implementation will be built against this same guarantee."""
    data = bytearray(build_fit.run_basic())
    for off in range(len(data)):
        data[off] ^= 0x08
        result = chiptime.parse(bytes(data))
        result.to_canonical_json()
        data[off] ^= 0x08  # restore
