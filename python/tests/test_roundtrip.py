"""Identity round-trip: parse → re-encode → parse must not lose anything.

This is the foundation the write verbs (repair, edit) stand on: if
re-encoding an untouched file drops or changes a field, every write path
silently damages healthy data. Born as a critique artifact for F26 and kept
as a permanent gate.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import chiptime
from chiptime.encode import encodable_from_message, encode_messages

REPO = Path(__file__).resolve().parents[2]
CORPUS = REPO / "corpus"


def _cases() -> list[tuple[str, Path]]:
    out = []
    for manifest, base in (
        (CORPUS / "MANIFEST.json", CORPUS),
        (CORPUS / "private" / "MANIFEST.json", CORPUS / "private"),
    ):
        if not manifest.exists():
            continue
        for rel in json.loads(manifest.read_text())["cases"]:
            path = base / rel / "input.fit"
            if path.exists():
                out.append((rel if base is CORPUS else f"private/{rel}", path))
    return out


CASES = _cases()


@pytest.mark.parametrize("rel,path", CASES, ids=[c[0] for c in CASES])
def test_identity_reencode_preserves_every_field(rel: str, path: Path) -> None:
    first = chiptime.parse(path, mode="lenient")
    if not first.messages:
        pytest.skip("no messages to re-encode (non-FIT or empty)")
    data = encode_messages([encodable_from_message(m) for m in first.messages])
    second = chiptime.parse(data, mode="lenient")

    assert len(second.messages) == len(first.messages), f"{rel}: message count changed"
    for a, b in zip(first.messages, second.messages, strict=True):
        assert a.name == b.name, f"{rel}: message identity changed"
        for fname, fv in a.fields.items():
            assert fname in b.fields, f"{rel}: {a.name}.{fname} lost on re-encode"
            got: Any = b.fields[fname].value
            assert got == fv.value, f"{rel}: {a.name}.{fname} {fv.value!r} -> {got!r}"


def test_repair_handles_reassembled_timestamp_field() -> None:
    """Regression: field 253 declared byte[4] and reassembled during decode
    must re-encode in canonical numeric form, not replay the source
    encoder's mistake (this raised EncodeError through v0.4.1)."""
    src = CORPUS / "cases" / "temporal" / "timestamp-as-bytes" / "input.fit"
    result = chiptime.repair(src)
    assert result.output_strict_ok
    reparsed = chiptime.parse(result.data, mode="strict")
    stamps = [m.get("timestamp") for m in reparsed.messages if m.name == "record"]
    assert stamps and all(s is not None for s in stamps)
    original = [m.get("timestamp") for m in chiptime.parse(src).messages if m.name == "record"]
    assert stamps == original, "repair must preserve reassembled timestamps exactly"
