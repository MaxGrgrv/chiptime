"""F22: fixes anchored to the issue-mining audit (docs/research/issue-mining-audit.md)."""

from itertools import pairwise

import build_fit

import chiptime


def test_timestamp16_rollover_merge() -> None:
    """fitdecode#28 / fitparse#46: t16 merges onto the rolling full timestamp."""
    result = chiptime.parse(build_fit.monitoring_t16())
    mons = [m for m in result.messages if m.name == "monitoring"]
    stamped = [m for m in mons if "timestamp" in m.fields]
    assert len(stamped) == 6  # 1 full + 5 merged
    raws = [m.get_raw("timestamp") for m in stamped]
    assert all(b - a == 8 for a, b in pairwise(raws))  # monotone ACROSS 0x10000
    assert any(
        p.code == "FIELD_RAW_SALVAGED" and "timestamp_16" in p.detail for p in result.provenance
    )


def test_hr_event_timestamp_12_expansion() -> None:
    """fitparse#122 (open there since 2019): packed 12-bit deltas with rollover."""
    result = chiptime.parse(build_fit.hr_plugin())
    hr = [m for m in result.messages if m.name == "hr"]
    expanded = next(m for m in hr if "event_timestamp_expanded" in m.fields)
    raws = expanded.fields["event_timestamp_expanded"].raw
    assert len(raws) == 8
    assert all(b > a for a, b in pairwise(raws))  # monotone through 0xFFF rollover
    assert raws[0] == 0xFFB0  # anchor 0xFFA0 -> delta 0xFB0
    assert raws[3] == 0x10010  # rollover applied
    vals = expanded.fields["event_timestamp_expanded"].value
    assert vals[0] == raws[0] / 1024.0  # seconds scaling


def test_left_right_balance_bits() -> None:
    """fitdecode#38 / fit-swift-sdk#13: flag bit + percent, never an enum."""
    result = chiptime.parse(build_fit.lr_balance())
    recs = [m for m in result.messages if m.name == "record"]
    assert recs[0].get("right_balance_pct") == 52.0
    assert recs[1].get("right_balance_pct") == 48.0
    assert recs[2].get("right_balance_pct") == 0.0  # the literal 0x80 case
    assert recs[2].get("left_right_balance") == 128  # raw preserved
    assert "right_balance_pct" not in recs[3].fields  # absent stays absent


def test_multi_string_split_and_padding() -> None:
    """muktihari#623/#436: arrays split; junk after final terminator ignored."""
    result = chiptime.parse(build_fit.multi_string())
    wkt = next(m for m in result.messages if m.name == "workout")
    assert wkt.get("wkt_name") == ["Open", "Water"]
    assert not any(w.code == "STRING_DECODE_REPLACED" for w in result.warnings)


def test_timestamp_declared_as_bytes() -> None:
    """fitdecode#33 (Xiaomi pipeline): byte[4] timestamps reassembled."""
    result = chiptime.parse(build_fit.ts_as_bytes())
    recs = [m for m in result.messages if m.name == "record"]
    raws = [m.get_raw("timestamp") for m in recs]
    assert raws == [raws[0] + i for i in range(4)]
    assert result.activity.sessions[0].derived.elapsed_time_s == 3.0
    assert any(w.code == "TIMESTAMP_DECLARED_AS_BYTES" for w in result.warnings)


def test_system_time_relative_timeline() -> None:
    """fitparse#3/#6 + taxonomy #39: relative timeline survives."""
    result = chiptime.parse(build_fit.system_time_only())
    s = result.activity.sessions[0]
    assert all(t is None for t in s.records.time)  # honest: no wall clock
    assert s.derived.elapsed_time_s == 29.0  # relative timeline kept
    assert any(w.code == "RELATIVE_TIMESTAMP" for w in result.warnings)


def test_float_sentinel_silent_nan_warned() -> None:
    """muktihari#39: only the exact all-ones pattern is the quiet sentinel."""
    result = chiptime.parse(build_fit.float_sentinel_vs_nan())
    unk = next(m for m in result.messages if m.name == "unknown_4242")
    assert unk.get("field_0") is None and unk.get("field_1") is None
    assert unk.get("field_2") == 2.5
    nonfinite = [w for w in result.warnings if w.code == "NONFINITE_FLOAT_NULLED"]
    assert len(nonfinite) == 1
    assert "field_1" in nonfinite[0].detail  # NaN warned; sentinel field_0 silent


def test_product_subfield_resolution() -> None:
    """fitparse PR#131: product resolved through garmin_product."""
    result = chiptime.parse(build_fit.ride_smooth())
    fid = next(m for m in result.messages if m.name == "file_id")
    assert fid.get("product") == "edge_530"
    assert fid.get_raw("product") == 3121  # raw always preserved


def test_encoder_float_invalid_exact_pattern() -> None:
    """fit_tool#35 / muktihari#39: absent floats encode as the all-ones pattern."""
    from chiptime.encode import EncodableMessage, FieldSpecValue, encode_messages

    data = encode_messages(
        [
            EncodableMessage(0, (FieldSpecValue(0, 0x00, 4, 1),)),
            EncodableMessage(4242, (FieldSpecValue(0, 0x88, None, 4),)),
        ]
    )
    assert b"\xff\xff\xff\xff" in data
    result = chiptime.parse(data)
    unk = next(m for m in result.messages if m.name == "unknown_4242")
    assert unk.get("field_0") is None
    assert not any(w.code == "NONFINITE_FLOAT_NULLED" for w in result.warnings)


def test_encoder_negative_values() -> None:
    """fit-cpp-sdk PR#9: negative scaled values must not collapse to 0."""
    from chiptime.encode import encodable_from_profile, encode_messages

    fid = encodable_from_profile(
        0,
        {
            "type": "activity",
            "manufacturer": "development",
            "time_created": build_fit.fit_ts(build_fit.T0),
        },
    )
    rec = encodable_from_profile(
        20, {"timestamp": build_fit.fit_ts(build_fit.T0), "temperature": -12, "grade": -8.5}
    )
    result = chiptime.parse(encode_messages([fid, rec]))
    r = next(m for m in result.messages if m.name == "record")
    assert r.get("temperature") == -12
    assert r.get("grade") == -8.5
