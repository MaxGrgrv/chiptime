import json
import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from chiptime.canonical import CanonicalizationError, dumps, number


def test_scalars() -> None:
    assert dumps(None) == b"null"
    assert dumps(True) == b"true"
    assert dumps(False) == b"false"
    assert dumps(42) == b"42"
    assert dumps(-7) == b"-7"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.0, "0"),
        (-0.0, "0"),
        (1.0, "1"),
        (1.5, "1.5"),
        (-1.5, "-1.5"),
        (0.001, "0.001"),
        (1e-6, "0.000001"),
        (1e-7, "1e-7"),
        (1e20, "100000000000000000000"),
        (1e21, "1e+21"),
        (1.5e16, "15000000000000000"),
        (5e-324, "5e-324"),
        (9007199254740991.0, "9007199254740991"),
        (123456789.123, "123456789.123"),
        (333333333.3333333, "333333333.3333333"),
    ],
)
def test_es6_number_vectors(value: float, expected: str) -> None:
    assert number(value) == expected


@given(st.floats(allow_nan=False, allow_infinity=False))
def test_number_round_trip(x: float) -> None:
    assert float(number(x)) == x


@given(st.floats(allow_nan=False, allow_infinity=False))
def test_number_is_valid_json(x: float) -> None:
    assert json.loads(number(x)) == pytest.approx(x, nan_ok=False) or json.loads(number(x)) == x


def test_rejects_nan_inf_bigint() -> None:
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(CanonicalizationError):
            dumps(bad)
    with pytest.raises(CanonicalizationError):
        dumps(2**53)
    assert dumps(2**53 - 1) == b"9007199254740991"


def test_string_escaping() -> None:
    assert dumps("a\nb") == b'"a\\nb"'
    assert dumps("\x07") == b'"\\u0007"'
    assert dumps("€") == '"€"'.encode()  # raw UTF-8, not \u-escaped


def test_key_sorting_utf16_code_units() -> None:
    # U+FF5F (single unit 0xFF5F) sorts AFTER U+1F600 (surrogates 0xD83D 0xDE00)
    # in UTF-16 order — the opposite of code-point order.
    out = dumps({"｟": 1, "\U0001f600": 2}).decode()
    assert out.index("\U0001f600") < out.index("｟")
    assert dumps({"b": 1, "a": 2}) == b'{"a":2,"b":1}'


def test_structures_and_type_guard() -> None:
    assert dumps({"z": [1, 2.5, None], "a": {"": ""}}) == b'{"a":{"":""},"z":[1,2.5,null]}'
    with pytest.raises(CanonicalizationError):
        dumps({1: "non-string key"})  # type: ignore[dict-item]
    with pytest.raises(CanonicalizationError):
        dumps(object())
