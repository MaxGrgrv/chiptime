"""Recovery-layer tests: resynchronization, preamble skip, salvage accounting."""

import build_fit
import corrupt
import pytest

import chiptime
from chiptime.errors import HeaderError, ProtocolError


def _records(result: chiptime.ParseResult) -> list:
    return [m for m in result.messages if m.name == "record"]


def test_undefined_local_resync_salvages_both_sides() -> None:
    result = chiptime.parse(build_fit.undefined_local())
    assert result.ok
    assert len(_records(result)) == 6  # 3 before + 3 after the corrupt span
    assert result.recovery is not None
    assert result.recovery.bytes_skipped == 11
    assert result.recovery.resync_count == 1
    assert any(p.code == "RESYNC_SKIPPED_BYTES" for p in result.provenance)
    with pytest.raises(ProtocolError) as ei:
        chiptime.parse(build_fit.undefined_local(), mode="strict")
    assert ei.value.code == "FIT_UNDEFINED_LOCAL_TYPE"


def test_garbage_block_midfile() -> None:
    data = corrupt.overwrite(build_fit.ride_smooth(), offset=1500, data="55" * 40)
    result = chiptime.parse(data)
    assert result.ok
    n = len(_records(result))
    assert 100 < n < 120  # most records survive a 40-byte trashed span
    assert result.recovery is not None and result.recovery.bytes_skipped > 40
    assert any(w.code == "FIT_CRC_MISMATCH" for w in result.warnings)  # flash damage
    with pytest.raises(ProtocolError):
        chiptime.parse(data, mode="strict")


def test_preamble_garbage_skip() -> None:
    data = corrupt.insert(build_fit.run_basic(), offset=0, repeat_byte=199, count=23)
    result = chiptime.parse(data)
    assert result.ok
    assert len(_records(result)) == 60  # nothing lost behind the junk
    assert any(p.code == "PREAMBLE_GARBAGE_SKIPPED" for p in result.provenance)
    with pytest.raises(HeaderError):
        chiptime.parse(data, mode="strict")


def test_frame_shift_reanchors_on_next_definition() -> None:
    result = chiptime.parse(build_fit.frame_shift())
    assert result.ok
    recs = _records(result)
    assert len(recs) >= 6  # 4 pre-shift + 2 after the re-anchoring definition
    assert result.recovery is not None and result.recovery.resync_count >= 1
    # the shifted region can masquerade as a bogus message — that's preserved,
    # honestly, for plausibility layers to flag (taxonomy #11 limitation)


def test_resync_never_fires_on_clean_files() -> None:
    for seed in ("ride_smooth", "run_basic", "redefinition_stress", "compressed_ts"):
        result = chiptime.parse(build_fit.build_seed(seed))
        assert result.recovery is None, seed
        assert not any(
            p.code in ("RESYNC_SKIPPED_BYTES", "PREAMBLE_GARBAGE_SKIPPED")
            for p in result.provenance
        ), seed
