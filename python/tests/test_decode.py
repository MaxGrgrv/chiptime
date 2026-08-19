"""Decode-core tests against the independent corpus fixture writer (ADR-0001 §3)."""

import struct

import build_fit  # corpus/tools, via conftest path
import pytest

import chiptime
from chiptime.errors import CrcMismatchError, EmptyFileError, TruncatedError


def _msgs(result: chiptime.ParseResult, name: str) -> list:
    return [m for m in result.messages if m.name == name]


def test_ride_smooth_clean() -> None:
    result = chiptime.parse(build_fit.ride_smooth())
    assert result.ok and not result.errors and result.recovery is None
    assert result.file_type == "activity"
    assert result.parts[0].file_id is not None
    assert result.parts[0].file_id["manufacturer"] == "garmin"
    records = _msgs(result, "record")
    assert len(records) == 120
    # scale/offset (#27): altitude (raw/5)-500, speed /1000, distance /100
    assert records[0].get("altitude") == 10.0
    assert records[0].get("speed") == 8.333
    assert records[0].get("distance") == 8.33
    # positions in degrees
    assert records[0].get("position_lat") == pytest.approx(52.37, abs=1e-5)
    # zero vs null (#64): coasting is REAL zero
    assert records[30].get("power") == 0
    # per-stream dropout (#68): power field absent entirely in records 50..55
    assert "power" not in records[52].fields
    assert records[52].get("heart_rate") is not None
    # timestamps ISO
    assert _msgs(result, "file_id")[0].get("time_created") == "2026-06-01T09:00:00Z"
    session = _msgs(result, "session")[0]
    assert session.get("sport") == "cycling"
    assert session.get("total_elapsed_time") == 120.0


def test_run_basic_clean() -> None:
    result = chiptime.parse(build_fit.run_basic())
    assert result.ok and not result.errors
    assert len(_msgs(result, "record")) == 60


def test_sentinels_become_none() -> None:
    b = build_fit.FitBuilder()
    t0 = build_fit.fit_ts(build_fit.T0)
    b.define(
        0,
        build_fit.FILE_ID,
        [(0, "enum", 1), (1, "uint16", 1), (3, "uint32z", 1), (4, "uint32", 1)],
    )
    b.data(0, 4, 1, None, t0)  # serial_number uint32z 0 → None
    b.define(1, build_fit.RECORD, build_fit.RECORD_FIELDS_FULL)
    b.data(1, t0, None, None, None, None, 85, 100, 8333, None, None)
    result = chiptime.parse(b.build())
    assert result.ok
    fid = _msgs(result, "file_id")[0]
    assert fid.get("serial_number") is None
    rec = _msgs(result, "record")[0]
    for f in ("position_lat", "position_long", "altitude", "heart_rate", "power", "temperature"):
        assert rec.get(f) is None, f
    assert rec.get("cadence") == 85


def test_compressed_timestamp_rollover() -> None:
    b = build_fit.FitBuilder()
    anchor = build_fit.fit_ts(build_fit.T0) & ~0x1F | 28  # low 5 bits = 28
    b.define(0, build_fit.FILE_ID, [(0, "enum", 1), (4, "uint32", 1)])
    b.data(0, 4, anchor - 100)
    b.define(2, build_fit.RECORD, [(253, "uint32", 1), (3, "uint8", 1)])
    b.data(2, anchor, 120)  # establishes the anchor
    b.define(1, build_fit.RECORD, [(3, "uint8", 1)])  # no timestamp field
    b.data_compressed(1, 29, 121)  # 29 >= 28 → same 32s window: +1
    b.data_compressed(1, 30, 122)  # +2
    b.data_compressed(1, 2, 123)  # 2 < 30 → rollover: anchor+6
    result = chiptime.parse(b.build())
    assert result.ok, result.errors
    recs = _msgs(result, "record")
    ts = [m.get_raw("timestamp") for m in recs]
    assert ts == [anchor, anchor + 1, anchor + 2, anchor + 6]


def test_local_redefinition() -> None:
    b = build_fit.FitBuilder()
    t0 = build_fit.fit_ts(build_fit.T0)
    b.define(0, build_fit.FILE_ID, [(0, "enum", 1), (4, "uint32", 1)])
    b.data(0, 4, t0)
    for i in range(6):  # hostile: local 0 remapped repeatedly (#20)
        if i % 2 == 0:
            b.define(0, build_fit.RECORD, [(253, "uint32", 1), (7, "uint16", 1)])
            b.data(0, t0 + i, 200 + i)
        else:
            b.define(0, build_fit.EVENT, [(253, "uint32", 1), (0, "enum", 1), (1, "enum", 1)])
            b.data(0, t0 + i, 0, 0)
    result = chiptime.parse(b.build())
    assert result.ok and not result.errors
    assert len(_msgs(result, "record")) == 3
    assert len(_msgs(result, "event")) == 3


def test_big_endian_definitions() -> None:
    b = build_fit.FitBuilder()
    t0 = build_fit.fit_ts(build_fit.T0)
    b.define(0, build_fit.FILE_ID, [(0, "enum", 1), (4, "uint32", 1)])
    b.data(0, 4, t0)
    b.define(1, build_fit.RECORD, [(253, "uint32", 1), (7, "uint16", 1)], big_endian=True)
    b.data(1, t0, 250)
    result = chiptime.parse(b.build())
    rec = _msgs(result, "record")[0]
    assert rec.get("power") == 250
    assert rec.get_raw("timestamp") == t0


def test_string_edges() -> None:
    b = build_fit.FitBuilder()
    b.define(0, build_fit.FILE_ID, [(0, "enum", 1), (8, "string", 8)])
    b.data(0, 4, "Edge")  # clean
    b.define(1, build_fit.DEVICE_INFO, [(27, "string", 4)])
    b.data(1, b"abcd")  # no NUL terminator (#33)
    b.define(2, build_fit.DEVICE_INFO, [(27, "string", 6)])
    b.data(2, b"ab\xffc\x00\x00")  # invalid UTF-8 (#33)
    result = chiptime.parse(b.build())
    assert result.ok
    assert _msgs(result, "file_id")[0].get("product_name") == "Edge"
    infos = _msgs(result, "device_info")
    assert infos[0].get("product_name") == "abcd"
    assert infos[1].get("product_name") == "ab�c"
    codes = {w.code for w in result.warnings}
    assert "STRING_UNTERMINATED" in codes and "STRING_DECODE_REPLACED" in codes


def test_array_sentinel_tail_trim() -> None:
    b = build_fit.FitBuilder()
    b.define(0, build_fit.FILE_ID, [(0, "enum", 1)])
    b.data(0, 4)
    b.define(1, build_fit.HRV, [(0, "uint16", 5)])
    b.data(1, [500, 520, 530, None, None])  # sentinel-padded tail (#34)
    result = chiptime.parse(b.build())
    hrv = _msgs(result, "hrv")[0]
    assert hrv.get("time") == [0.5, 0.52, 0.53]


def test_unknown_message_and_fields_preserved() -> None:
    b = build_fit.FitBuilder()
    b.define(0, build_fit.FILE_ID, [(0, "enum", 1), (99, "uint16", 1)])
    b.data(0, 4, 777)
    b.define(1, 4242, [(0, "uint16", 1), (1, "uint64", 1)])
    b.data(1, 55, 2**60)
    result = chiptime.parse(b.build())
    assert result.ok
    assert _msgs(result, "file_id")[0].get("field_99") == 777  # unknown field (#23)
    unk = _msgs(result, "unknown_4242")[0]
    assert unk.get("field_0") == 55
    assert unk.get("field_1") == 2**60
    d = result.to_dict()
    part_msgs = d["parts"][0]["messages"]
    big = next(m for m in part_msgs if m["name"] == "unknown_4242")
    assert big["fields"]["field_1"]["value"] == "1152921504606846976"  # 64-bit → string


def test_nonfinite_floats_nulled() -> None:
    b = build_fit.FitBuilder()
    b.define(0, build_fit.FILE_ID, [(0, "enum", 1)])
    b.data(0, 4)
    b.define(1, 4242, [(0, "float32", 1), (1, "float64", 1), (2, "float32", 1)])
    b.data(1, float("nan"), float("inf"), 1.5)
    result = chiptime.parse(b.build())
    unk = _msgs(result, "unknown_4242")[0]
    assert unk.get("field_0") is None and unk.get("field_1") is None
    assert unk.get("field_2") == 1.5
    assert any(w.code == "NONFINITE_FLOAT_NULLED" for w in result.warnings)


def test_invalid_base_type_field_salvage() -> None:
    b = build_fit.FitBuilder()
    b.define(0, build_fit.FILE_ID, [(0, "enum", 1)])
    b.data(0, 4)
    # Hand-craft: record definition with field 7 declaring bogus base type 0x7B (#25)
    b.raw(bytes([0x41, 0, 0]) + struct.pack("<H", 20) + bytes([2, 253, 4, 0x86, 7, 2, 0x7B]))
    b.raw(bytes([0x01]) + struct.pack("<I", build_fit.fit_ts(build_fit.T0)) + b"\xde\xad")
    result = chiptime.parse(b.build())
    assert result.ok
    rec = _msgs(result, "record")[0]
    assert rec.get("power") is None
    assert rec.get_raw("power") == b"\xde\xad"
    assert any(p.code == "FIELD_RAW_SALVAGED" for p in result.provenance)


def test_truncated_mid_record() -> None:
    data = build_fit.ride_smooth()[:-13]  # cuts inside the last record + removes CRC
    result = chiptime.parse(data)
    assert result.ok
    assert result.recovery is not None
    assert result.recovery.recovered_records > 100
    assert result.recovery.estimated_total_records is not None
    assert any(p.code == "TRUNCATED_TAIL_SALVAGED" for p in result.provenance)
    with pytest.raises(TruncatedError) as ei:
        chiptime.parse(data, mode="strict")
    assert ei.value.code == "FIT_TRUNCATED"
    assert ei.value.suggestion is not None


def test_undefined_local_type_salvage() -> None:
    b = build_fit.FitBuilder()
    b.define(0, build_fit.FILE_ID, [(0, "enum", 1), (4, "uint32", 1)])
    b.data(0, 4, build_fit.fit_ts(build_fit.T0))
    b.raw(bytes([0x07]))  # data message for never-defined local 7 (#19)
    result = chiptime.parse(b.build())
    assert result.ok
    assert len(result.messages) == 1
    # F5: no anchor exists after the bad byte, so resync skips to end of body
    assert any(p.code == "RESYNC_SKIPPED_BYTES" for p in result.provenance)
    assert result.recovery is not None and result.recovery.bytes_skipped == 1


def test_file_crc_bad_lenient_vs_strict() -> None:
    import corrupt

    data = corrupt.break_file_crc(build_fit.ride_smooth())
    result = chiptime.parse(data)
    assert result.ok and result.recovery is None
    assert any(w.code == "FIT_CRC_MISMATCH" for w in result.warnings)
    with pytest.raises(CrcMismatchError):
        chiptime.parse(data, mode="strict")


def test_header_crc_zero_is_legal() -> None:
    b = build_fit.FitBuilder()
    b.define(0, build_fit.FILE_ID, [(0, "enum", 1)])
    b.data(0, 4)
    data = b.build(header_crc="zero")
    result = chiptime.parse(data)
    assert result.ok and not result.warnings and not result.errors


def test_empty_file() -> None:
    result = chiptime.parse(b"")
    assert not result.ok
    assert result.errors[0].code == "FIT_EMPTY"
    with pytest.raises(EmptyFileError):
        chiptime.parse(b"", mode="strict")


def test_strip_pii() -> None:
    b = build_fit.FitBuilder()
    t0 = build_fit.fit_ts(build_fit.T0)
    b.define(0, build_fit.FILE_ID, [(0, "enum", 1), (3, "uint32z", 1), (4, "uint32", 1)])
    b.data(0, 4, 987654, t0)
    b.define(1, 3, [(1, "enum", 1), (4, "uint16", 1)])  # user_profile: gender, weight
    b.data(1, 1, 703)
    result = chiptime.parse(b.build(), strip_pii=True)
    assert not _msgs(result, "user_profile")
    assert _msgs(result, "file_id")[0].get("serial_number") is None
    assert any(p.code == "PII_STRIPPED" for p in result.provenance)


def test_determinism_across_processes_shape() -> None:
    data = build_fit.ride_smooth()
    a = chiptime.parse(data).to_canonical_json()
    b = chiptime.parse(data).to_canonical_json()
    assert a == b
    assert b"path" not in a  # source path never serialized (ADR-0002)
