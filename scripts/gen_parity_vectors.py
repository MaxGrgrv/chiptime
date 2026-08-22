#!/usr/bin/env python3
"""Generate the Python↔TypeScript differential vectors (F31, ADR-0009 §4).

Run from repo root:  uv run --project python python scripts/gen_parity_vectors.py
CI regenerates and fails on any diff, so a Python-side behavior change cannot
silently invalidate the recorded contract.

Writes js/test/vectors/:
  canonical-ok.json         inputs both languages accept; `expected` is CPython's exact output
  canonical-refuse.json     inputs both languages must refuse
  canonical-asymmetry.json  inputs CPython accepts and TypeScript cannot (documented, tested)
  numeric.json              per-function input/output pairs for the number kernel

Inputs are stored as *JSON text*, not as decoded values: each side parses with its
own JSON reader and serializes with its own canonicalizer, so the harness measures
the thing that actually has to match. Deterministic: no wall clock, no randomness.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "python" / "src"))

from chiptime.canonical import CanonicalizationError, dumps  # isort:skip

OUT = pathlib.Path(__file__).resolve().parents[1] / "js" / "test" / "vectors"
NAN = float("nan")

# ── canonical: inputs as JSON text ──────────────────────────────────────────────
# Every entry is (name, json_text). Grouped by what it is meant to catch.
CANONICAL_INPUTS: list[tuple[str, str]] = [
    # -- literals ---------------------------------------------------------------
    ("null", "null"),
    ("true", "true"),
    ("false", "false"),
    ("empty-object", "{}"),
    ("empty-array", "[]"),
    # -- integers ---------------------------------------------------------------
    ("int-zero", "0"),
    ("int-negative-zero", "-0"),
    ("int-one", "1"),
    ("int-negative", "-1"),
    ("int-max-safe", "9007199254740991"),
    ("int-min-safe", "-9007199254740991"),
    # -- floats: the formatting boundaries ES6 and Python must agree on ---------
    ("float-zero", "0.0"),
    ("float-negative-zero", "-0.0"),
    ("float-integral", "1.0"),
    ("float-half", "1.5"),
    ("float-tenth", "0.1"),
    ("float-third", "0.3333333333333333"),
    ("float-1e-6", "0.000001"),
    ("float-1e-7", "1e-7"),
    ("float-1e-21", "1e-21"),
    ("float-smallest-subnormal", "5e-324"),
    ("float-exponent-boundary-low", "0.000001"),
    ("float-repr-shortest", "0.30000000000000004"),
    ("float-negative", "-2.5"),
    ("float-large-non-integral", "4503599627370495.5"),
    # -- strings: escaping ------------------------------------------------------
    ("string-empty", '""'),
    ("string-ascii", '"abc"'),
    ("string-quote-backslash", '"a\\"b\\\\c"'),
    ("string-control-chars", '"\\u0000\\u0001\\u001f"'),
    ("string-named-escapes", '"\\b\\f\\n\\r\\t"'),
    ("string-del-is-literal", '"\\u007f"'),
    ("string-latin1", '"\\u00e9"'),
    ("string-cjk", '"\\u65e5\\u672c"'),
    ("string-astral-emoji", '"\\ud83d\\ude80"'),
    ("string-combining-mark", '"e\\u0301"'),
    ("string-nel-and-nbsp", '"\\u0085\\u00a0"'),
    # -- key ordering: UTF-16 code units, not code points -----------------------
    ("keys-ascii-case", '{"b":1,"A":2,"a":3,"B":4}'),
    ("keys-empty-and-short", '{"":1,"a":2,"aa":3}'),
    ("keys-digits-vs-letters", '{"1":1,"10":2,"2":3,"a":4}'),
    (
        "keys-code-unit-vs-code-point",
        # U+FF3A sorts *after* U+10000 by code unit (0xD800 < 0xFF3A) and *before*
        # it by code point (65338 < 65536). This vector is the whole reason JCS
        # says "UTF-16 code units" out loud.
        '{"\\uff3a":1,"\\ud800\\udc00":2}',
    ),
    ("keys-astral-vs-bmp", '{"\\ud83d\\ude80":1,"z":2,"\\uffff":3}'),
    # -- integer-like object keys: JS reorders these on plain objects -----------
    ("keys-integer-like", '{"2":"b","1":"a","10":"c","0":"z"}'),
    # -- nesting ----------------------------------------------------------------
    ("nested-mixed", '{"b":[1,2.5,null,true],"a":{"z":1,"y":[{"k":"v"}]}}'),
    ("array-of-objects", '[{"b":1,"a":2},{"a":3}]'),
    ("deep-nesting", '{"a":{"a":{"a":{"a":{"a":[1,[2,[3,[4]]]]}}}}}'),
    # -- a shape resembling real canonical output -------------------------------
    (
        "streams-like",
        '{"chiptime_schema":1,"ok":true,"streams":{"power":{"units":"W",'
        '"values":[212,0,null,65.5],"source":"native"}},"errors":[]}',
    ),
]

# Both languages must refuse these.
CANONICAL_REFUSALS: list[tuple[str, str]] = [
    ("int-above-max-safe", "9007199254740992"),
    ("int-below-min-safe", "-9007199254740992"),
    ("int-far-above-max-safe", "123456789012345678901234567890"),
    ("int-nested-above-max-safe", '{"a":[1,9007199254740992]}'),
]

# CPython accepts these; TypeScript cannot tell an integral float from an int and
# refuses them. Recorded so the asymmetry is a tested fact, not a footnote.
# See F31 spec Risk 1: no corpus snapshot contains a number in this band.
CANONICAL_ASYMMETRY: list[tuple[str, str]] = [
    ("float-two-to-the-53", "9007199254740992.0"),
    ("float-1e16", "1e16"),
    ("float-1e21", "1e21"),
    ("float-1e20-with-digits", "1.00000000000001e20"),
    ("float-max", "1.7976931348623157e308"),
    ("float-rounds-up-to-integral", "9007199254740991.5"),
]


def canonical_vectors() -> None:
    ok = []
    for name, text in CANONICAL_INPUTS:
        value = json.loads(text)
        ok.append({"name": name, "input": text, "expected": dumps(value).decode("utf-8")})

    refuse = []
    for name, text in CANONICAL_REFUSALS:
        try:
            dumps(json.loads(text))
        except CanonicalizationError as exc:
            refuse.append({"name": name, "input": text, "pythonError": str(exc)})
        else:  # pragma: no cover - vector authoring error
            raise SystemExit(f"refusal vector {name!r} was accepted by canonical.dumps")

    asym = []
    for name, text in CANONICAL_ASYMMETRY:
        asym.append(
            {
                "name": name,
                "input": text,
                "pythonOutput": dumps(json.loads(text)).decode("utf-8"),
                "note": "every finite double >= 2**53 is integral, so TypeScript's value-based "
                "guard refuses the whole range while Python's type-based guard accepts it as a "
                "float (ADR-0009 §4, F31 Risk 1)",
            }
        )

    _write("canonical-ok.json", ok)
    _write("canonical-refuse.json", refuse)
    _write("canonical-asymmetry.json", asym)


# ── numeric kernel ──────────────────────────────────────────────────────────────
ROUND_INPUTS = [
    0.0,
    -0.0,
    0.5,
    -0.5,
    1.5,
    -1.5,
    2.5,
    -2.5,
    3.5,
    4.5,
    0.49999999999999994,
    -0.49999999999999994,
    1.0,
    1.4999999999999998,
    2.675,
    -2.675,
    1e15 + 0.5,
    123.456,
    -123.456,
    0.1,
    1e-9,
    8.5,
    9.5,
    -8.5,
    -9.5,
]

ROUND_N_INPUTS = [
    # (x, n) — the ties are the point: toFixed rounds these away from zero.
    (0.125, 2),
    (0.375, 2),
    (0.135, 2),
    (2.5, 0),
    (-2.5, 0),
    (0.5, 0),
    (1.5, 0),
    (2.675, 2),
    (-2.675, 2),
    (1.005, 2),
    (2.665, 2),
    (1.0049999999999999, 2),
    (0.0, 2),
    (-0.0, 2),
    (33.33333333333333, 3),
    (-33.33333333333333, 3),
    (99.995, 2),
    (0.049999999999999996, 1),
    (1234.5678, 1),
    (1234.5678, 4),
    (65535.0, 1),
    (3.6, 2),
    (12.345678, 4),
    (0.1 + 0.2, 3),
    (1e-7, 4),
    (5.551115123125783e-17, 4),
    (180.0, 3),
    (-180.0, 3),
]

DIVMOD_INPUTS = [
    (7, 3),
    (-7, 3),
    (7, -3),
    (-7, -3),
    (0, 3),
    (86400, 3600),
    (-1, 86400),
    (631065600, 86400),
    (-631065600, 86400),
    (5, 5),
    (-5, 5),
    (1, 2),
    (-1, 2),
]


def numeric_vectors() -> None:
    data = {
        "pyRound": [[x, round(x)] for x in ROUND_INPUTS],
        "pyRoundN": [[x, n, round(x, n)] for x, n in ROUND_N_INPUTS],
        "floorDiv": [[a, b, a // b] for a, b in DIVMOD_INPUTS],
        "divmod": [[a, b, list(divmod(a, b))] for a, b in DIVMOD_INPUTS],
    }
    _write("numeric.json", data)


def base_type_vectors() -> None:
    """is_invalid() for every base type against its sentinel and its neighbours (F32).

    Values travel as decimal strings: uint64's sentinel is 0xFFFFFFFFFFFFFFFF, which
    no JSON number can carry (ADR-0009 s4). TypeScript rebuilds a bigint for the
    64-bit rows and a number for the rest.
    """
    from chiptime.profile.base_types import BASE_TYPES, is_invalid

    rows = []
    for byte in sorted(BASE_TYPES):
        bt = BASE_TYPES[byte]
        probes: list[float | int] = [0, 1, -1]
        if bt.invalid is not None:
            probes += [bt.invalid, bt.invalid - 1, bt.invalid + 1]
            signed = {"sint8": 0x7F, "sint16": 0x7FFF, "sint32": 0x7FFFFFFF}
            if bt.name in signed:
                probes.append(signed[bt.name])
        for value in probes:
            rows.append(
                {
                    "type": bt.name,
                    "byte": bt.byte,
                    "value": str(value),
                    "expected": is_invalid(bt, value),
                }
            )
        # NaN is the sentinel's real form for the float types; every type gets asked.
        rows.append(
            {"type": bt.name, "byte": bt.byte, "value": "nan", "expected": is_invalid(bt, NAN)}
        )
    _write("base-types.json", rows)


def utf8_vectors() -> None:
    """bytes.decode("utf-8", errors="replace") over adversarial sequences (F34).

    CPython and the WHATWG TextDecoder agree today, including on the maximal-subpart
    cases where they could have disagreed about how many U+FFFD to emit. Recorded so
    a runtime change fails a test rather than silently altering decoded strings.
    """
    probes = [
        b"",
        b"abc",
        b"\xc3\xa9",
        b"\xe6\x97\xa5\xe6\x9c\xac",
        b"\xf0\x9f\x9a\x80",
        b"\xf0\x80\x80\x41",
        b"\xe0\x80\x80",
        b"\xff\xfe",
        b"\x80",
        b"\xc3",
        b"\xed\xa0\x80",
        b"\xf4\x90\x80\x80",
        b"abc\xff\xffdef",
        b"\xe2\x82",
        b"\xc0\xaf",
        b"\xf8\x88\x80\x80\x80",
        b"a\x00b",
        b"\x00",
        b"\x7f\x80\x81",
    ]
    # Recorded from the decoder's own string path, not from bytes.decode(): the
    # segmentation rules (terminated segments, padding junk, empty-segment stop) are
    # part of what has to match, and a raw-decode vector would test TextDecoder in
    # isolation while missing them.
    from chiptime.decode import Decoder

    rows = []
    for probe in probes:
        # Reaching into the private method deliberately: the vector must record what the
        # decoder's string path produces, not what a public wrapper would reshape.
        fvalue = Decoder()._string(probe, "m", "f")
        rows.append({"hex": probe.hex(), "value": fvalue.value})
    _write("utf8.json", rows)


def timestamp_vectors() -> None:
    """fit_ts_to_iso / _local across the epoch, leap years and the uint32 ceiling (F34)."""
    from chiptime.decode import fit_ts_to_iso, fit_ts_to_iso_local

    probes = [
        0,
        1,
        59,
        60,
        3599,
        3600,
        86399,
        86400,
        268435456,
        1149238800,
        # leap-year and century boundaries, measured from the FIT epoch
        63072000,
        946684800,
        951782400,
        4102444800,
        0xFFFFFFFE,
    ]
    _write(
        "timestamps.json",
        [{"fit": p, "iso": fit_ts_to_iso(p), "local": fit_ts_to_iso_local(p)} for p in probes],
    )


def inflate_vectors() -> None:
    """DEFLATE/gzip vectors from CPython's zlib (F35, amendment D3).

    inflate.ts is the one module with no Python twin, and the corpus reaches it
    through two cases. DEFLATE has three block types and an implementation that gets
    stored and fixed-Huffman right would pass both, so the probes force all three:
    level 0 emits stored blocks, tiny inputs emit fixed-Huffman, and varied input
    emits dynamic-Huffman. Long repetitive inputs push back-references past the
    32 KiB window.
    """
    import zlib

    probes: list[tuple[str, bytes]] = [
        ("empty", b""),
        ("one-byte", b"A"),
        ("tiny", b"hello"),
        ("ascii", b"the quick brown fox jumps over the lazy dog" * 3),
        ("repetitive", b"ABCD" * 5000),  # back-references far past the window
        ("window-crossing", bytes(range(256)) * 200),
        ("incompressible", bytes((i * 2654435761) % 256 for i in range(70000))),
        ("nul-heavy", bytes(40000)),
        ("fit-like", b"\x0e\x10\x9c\x08" + bytes(range(64)) * 500),
    ]
    rows = []
    for name, raw in probes:
        for level in range(10):
            co = zlib.compressobj(level, zlib.DEFLATED, -15)  # raw deflate
            deflated = co.compress(raw) + co.flush()
            rows.append(
                {
                    "name": f"{name}@{level}",
                    "deflate": deflated.hex(),
                    "gzip": zlib.compress(raw, level).hex(),  # zlib wrapper
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size": len(raw),
                }
            )
    _write("inflate.json", rows)

    # Corrupt streams, recorded against the API intake actually uses. gzip.decompress
    # requires a complete stream, unlike zlib.decompressobj which happily returns a
    # partial result -- comparing against the wrong one would have taught the port the
    # wrong lenience.
    import gzip as gziplib

    payload = b"the quick brown fox" * 50
    whole = zlib.compress(payload, 6)  # zlib wrapper, as gzip.compress-like
    # mtime=0: gzip.compress stamps a wall clock into the header otherwise, which
    # would make this generator nondeterministic -- the one thing the whole project
    # forbids, caught by the vector-freshness gate.
    gz = gziplib.compress(payload, mtime=0)
    variants = [
        ("gz-truncated-half", gz[: len(gz) // 2]),
        ("gz-truncated-header", gz[:3]),
        ("gz-empty", b""),
        ("gz-garbage", bytes.fromhex("deadbeefcafebabe")),
        ("gz-bad-magic", b"XX" + gz[2:]),
        ("gz-flipped-body", gz[:20] + bytes([gz[20] ^ 0xFF]) + gz[21:]),
        ("zlib-truncated", whole[: len(whole) // 2]),
    ]
    rows = []
    for name, blob in variants:
        try:
            gziplib.decompress(blob) if name.startswith("gz") else zlib.decompress(blob)
            raises = False
        except Exception:
            raises = True
        rows.append({"name": name, "hex": blob.hex(), "pythonRaises": raises})
    _write("inflate-bad.json", rows)


def sha256_vectors() -> None:
    """SHA-256 over byte patterns spanning the block and length-field boundaries."""
    probes = [b"", b"a", b"abc", b"\x00", bytes(range(256))]
    probes += [bytes(n) for n in (55, 56, 57, 63, 64, 65, 119, 120, 127, 128, 129, 1000)]
    probes += [b"the quick brown fox" * 100]
    _write(
        "sha256.json",
        [{"hex": p.hex(), "digest": hashlib.sha256(p).hexdigest()} for p in probes],
    )


def format_vectors() -> None:
    """pySum / pyFixed / pyFloatStr against CPython (F36).

    sum() is the least obvious of the three: since CPython 3.12 its float fast path
    runs compensated (Neumaier) summation, not a loop of additions, and the
    difference reaches canonical output through every derived average.
    """
    sums = [
        [8.333] * 120,
        [0.1] * 1000,
        [1e16, 1.0, -1e16],
        [0.1, 0.2, 0.3],
        [],
        [1.0],
        [1e290, 1e290, -1e290],  # large but finite; JSON cannot carry Infinity
        [3.6, 3.6, 3.6, 3.6, 3.6, 3.6, 3.6],
        [0.7, 0.1, 0.3, 0.9, 0.5] * 40,
    ]
    fixed_vals = [
        0.125,
        0.135,
        2.5,
        2.675,
        1.005,
        0.0,
        -0.0,
        230.0,
        55.0,
        20.04,
        99.995,
        1234.5678,
        -2.5,
        -0.125,
        3.14159,
        0.05,
        0.15,
        0.25,
        12.0,
    ]
    _write(
        "format.json",
        {
            "pySum": [{"values": vals, "sum": sum(vals)} for vals in sums],
            "pyFixed": [
                {"x": v, "n": n, "text": f"{v:.{n}f}"} for v in fixed_vals for n in (0, 1, 2, 3)
            ],
            "pyFloatStr": [{"x": v, "text": str(v)} for v in fixed_vals],
        },
    )


def crc_vectors() -> None:
    """crc16 over adversarial byte patterns (F33).

    The CRC is a byte-wise table composed from the FIT nibble algorithm; a table
    built wrong is wrong only for some inputs, so the probes sweep single bytes,
    every-byte-value runs, and lengths around the table boundaries.
    """
    from chiptime.frames import crc16

    probes: list[bytes] = [b"", b"\x00", b"\xff", b".FIT", bytes(range(256))]
    probes += [bytes([v]) * n for v in (0x00, 0x01, 0x7F, 0x80, 0xFF) for n in (1, 2, 15, 16, 17)]
    probes += [bytes(range(n)) for n in (12, 14, 255)]
    rows = [{"hex": p.hex(), "crc": crc16(p)} for p in probes]
    # Seeded continuation: crc16(b, crc) must chain like the Python default argument.
    rows.append({"hex": b"abc".hex(), "seed": crc16(b"xyz"), "crc": crc16(b"abc", crc16(b"xyz"))})
    _write("crc16.json", rows)


def _write(name: str, payload: object) -> None:
    path = OUT / name
    # allow_nan=False: json.dumps writes bare NaN/Infinity by default, which no
    # JSON parser accepts. A vector file that cannot be read is worse than a
    # missing one, so this fails at generation rather than at test time.
    text = json.dumps(payload, indent=2, ensure_ascii=True, allow_nan=False)
    path.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {path.relative_to(pathlib.Path.cwd())}")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    canonical_vectors()
    numeric_vectors()
    base_type_vectors()
    crc_vectors()
    utf8_vectors()
    timestamp_vectors()
    inflate_vectors()
    sha256_vectors()
    format_vectors()


if __name__ == "__main__":
    main()
