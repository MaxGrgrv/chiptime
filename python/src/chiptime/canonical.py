"""RFC 8785 (JCS) canonical JSON serialization — the determinism contract.

See ADR-0002. Accepts only None/bool/int/float/str/list/dict trees. Refuses
NaN/Infinity and integers beyond +/-(2**53 - 1): those must be handled by the
shaping layer (null with diagnostic, or decimal string) before serialization.
"""

from __future__ import annotations

from typing import Any

MAX_SAFE_INT = 2**53 - 1

_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


class CanonicalizationError(ValueError):
    """A value that must never reach serialization did (bug guard, ADR-0002)."""


def dumps(obj: Any) -> bytes:
    """Serialize to canonical JSON bytes (UTF-8, JCS rules)."""
    parts: list[str] = []
    _write(obj, parts)
    return "".join(parts).encode("utf-8")


def _write(obj: Any, out: list[str]) -> None:
    if obj is None:
        out.append("null")
    elif obj is True:
        out.append("true")
    elif obj is False:
        out.append("false")
    elif isinstance(obj, str):
        out.append(_string(obj))
    elif isinstance(obj, int):  # bool handled above
        if abs(obj) > MAX_SAFE_INT:
            raise CanonicalizationError(
                f"integer {obj} exceeds 2**53-1; shape layer must serialize it as a string"
            )
        out.append(str(obj))
    elif isinstance(obj, float):
        out.append(number(obj))
    elif isinstance(obj, list):
        out.append("[")
        for i, item in enumerate(obj):
            if i:
                out.append(",")
            _write(item, out)
        out.append("]")
    elif isinstance(obj, dict):
        out.append("{")
        keys = list(obj.keys())
        for k in keys:
            if not isinstance(k, str):
                raise CanonicalizationError(f"non-string key {k!r}")
        # JCS: sort by UTF-16 code units, not code points.
        keys.sort(key=lambda s: s.encode("utf-16-be"))
        for i, k in enumerate(keys):
            if i:
                out.append(",")
            out.append(_string(k))
            out.append(":")
            _write(obj[k], out)
        out.append("}")
    else:
        raise CanonicalizationError(f"unserializable type {type(obj).__name__}")


def _string(s: str) -> str:
    out = ['"']
    for ch in s:
        esc = _ESCAPES.get(ch)
        if esc is not None:
            out.append(esc)
        elif ch < "\x20":
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def number(x: float) -> str:
    """Format a float per ECMAScript Number::toString (JCS requirement)."""
    if x != x or x in (float("inf"), float("-inf")):
        raise CanonicalizationError(
            "NaN/Infinity must be nulled (with a diagnostic) before serialization"
        )
    if x == 0.0:
        return "0"  # covers -0.0 too
    if x < 0:
        return "-" + number(-x)

    # Python repr is shortest-round-trip, same digit selection as ES6;
    # only the presentation rules differ. Parse repr into digits + exponent.
    r = repr(x)
    mantissa, _, exp_s = r.partition("e")
    exp = int(exp_s) if exp_s else 0
    int_part, _, frac_part = mantissa.partition(".")
    digits = (int_part + frac_part).lstrip("0")
    exp10 = exp - len(frac_part)  # value == int(digits) * 10**exp10 (pre-strip)
    stripped = len(digits) - len(digits.rstrip("0"))
    digits = digits.rstrip("0")
    exp10 += stripped

    k = len(digits)
    n = exp10 + k  # value == 0.digits * 10**n

    if k <= n <= 21:
        return digits + "0" * (n - k)
    if 0 < n <= 21:
        return digits[:n] + "." + digits[n:]
    if -6 < n <= 0:
        return "0." + "0" * (-n) + digits
    # exponential form: d[.ddd]e±(n-1)
    head = digits[0] if k == 1 else digits[0] + "." + digits[1:]
    e = n - 1
    return f"{head}e{'+' if e >= 0 else '-'}{abs(e)}"
