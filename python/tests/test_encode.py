"""Encoder tests (ADR-0006): round trips, strict cleanliness, synthesis, slots."""

import copy

import build_fit
import pytest

import chiptime
from chiptime.encode import (
    EncodableMessage,
    EncodeError,
    FieldSpecValue,
    encodable_from_message,
    encodable_from_profile,
    encode_messages,
)


def _semantic(result: chiptime.ParseResult) -> object:
    d = result.to_dict()
    del d["source"]

    def strip(o: object) -> object:
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if k != "offset"}
        if isinstance(o, list):
            return [strip(v) for v in o]
        return o

    return strip(d)


@pytest.mark.parametrize(
    "seed",
    [
        "ride_smooth",
        "dev_fields_stryd",
        "multisport",
        "compressed_ts",
        "big_endian_mixed",
        "uint64_fields",
    ],
)
def test_round_trip_semantic_identity(seed: str) -> None:
    original = chiptime.parse(build_fit.build_seed(seed))
    all_msgs = [m for part in original.parts for m in part.messages]
    reencoded = encode_messages([encodable_from_message(m) for m in all_msgs])
    reparsed = chiptime.parse(reencoded)
    assert _semantic(reparsed) == _semantic(original)


@pytest.mark.parametrize("seed", ["ride_smooth", "dev_fields_stryd", "multisport"])
def test_reencoded_files_are_strict_clean(seed: str) -> None:
    original = chiptime.parse(build_fit.build_seed(seed))
    reencoded = encode_messages([encodable_from_message(m) for m in original.messages])
    strict = chiptime.parse(reencoded, mode="strict")  # must not raise: wire-clean
    assert strict.ok
    # semantic warnings may persist (they describe the DATA); the encoder must
    # not introduce any NEW warning class
    assert {w.code for w in strict.warnings} <= {
        w.code for w in chiptime.parse(build_fit.build_seed(seed)).warnings
    }


def test_encoder_deterministic() -> None:
    original = chiptime.parse(build_fit.ride_smooth())
    ems = [encodable_from_message(m) for m in original.messages]
    assert encode_messages(ems) == encode_messages(copy.deepcopy(ems))


def test_profile_synthesis_round_trip() -> None:
    em = encodable_from_profile(
        18,
        {  # session
            "timestamp": build_fit.fit_ts(build_fit.T0) + 100,
            "start_time": build_fit.fit_ts(build_fit.T0),
            "sport": "cycling",
            "total_elapsed_time": 100.0,
            "total_distance": 833.0,
            "avg_power": 210,
            "message_index": 0,
        },
    )
    fid = encodable_from_profile(
        0,
        {
            "type": "activity",
            "manufacturer": "development",
            "time_created": build_fit.fit_ts(build_fit.T0),
        },
    )
    result = chiptime.parse(encode_messages([fid, em]))
    assert result.ok
    s = result.activity.sessions[0]
    assert s.sport == "cycling"
    assert s.declared is not None
    assert s.declared.elapsed_time_s == 100.0
    assert s.declared.distance_m == 833.0
    assert s.declared.avg["power"] == 210


def test_slot_eviction_over_16_shapes() -> None:
    msgs = []
    for i in range(20):  # 20 distinct shapes force deterministic eviction
        msgs.append(EncodableMessage(1000 + i, (FieldSpecValue(0, 0x84, i, 2),)))
    msgs.append(EncodableMessage(1000, (FieldSpecValue(0, 0x84, 99, 2),)))  # re-define
    result = chiptime.parse(encode_messages(msgs))
    assert result.ok
    assert len(result.messages) == 21
    assert result.messages[-1].get("field_0") == 99


def test_encode_errors_are_typed() -> None:
    with pytest.raises(EncodeError):
        encodable_from_profile(18, {"no_such_field": 1})
    with pytest.raises(EncodeError):
        encode_messages([EncodableMessage(20, (FieldSpecValue(0, 0x84, 2**40, 2),))])
