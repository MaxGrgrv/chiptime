#!/usr/bin/env python3
"""Transcode the machine-readable code registries into TypeScript (F33).

Run from repo root:  uv run --project python python scripts/gen_codes_ts.py
CI regenerates and fails on any diff.

These 103 strings are an agent-facing contract: docs/for-agents.md is generated
from the same tables, and consumers branch on the codes. Hand-copying them into a
second language would drift on the first Python edit, so they follow F32's
transcoding precedent rather than F31's hand-porting one.

The error *classes* stay hand-written in errors.ts. This file emits the
defect-code-to-class mapping as a string kind rather than a class reference, so the
generated module imports nothing and no cycle exists.

Deterministic: sorted keys, no wall clock.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "python" / "src"))

from chiptime.errors import (  # isort:skip
    ERROR_CODES,
    PROVENANCE_CODES,
    WARNING_CODES,
    _DEFECT_ERROR_CLASS,
)

OUT = pathlib.Path(__file__).resolve().parents[1] / "js" / "src" / "codes.ts"

HEADER = """/**
 * GENERATED FILE -- do not edit. Regenerate with:
 *
 *     uv run --project python python scripts/gen_codes_ts.py
 *
 * The machine-readable code registries, transcoded from `python/src/chiptime/errors.py`
 * so the two languages cannot disagree about a contract consumers branch on
 * (contract #5; `docs/for-agents.md` is generated from the same tables).
 *
 * The error classes themselves live in `errors.ts`, hand-written. This module emits
 * the defect-to-class mapping as a string kind rather than a class reference, so it
 * imports nothing and there is no cycle.
 */

/** Which `FitError` subclass a defect code maps to. Resolved in `errors.ts`. */
export type ErrorKind =
  | "NotFitError"
  | "EmptyFileError"
  | "HeaderError"
  | "TruncatedError"
  | "CrcMismatchError"
  | "ProtocolError";
"""


def table(name: str, mapping: dict[str, str], doc: str) -> str:
    lines = [f"\n/** {doc} */", f"export const {name}: Readonly<Record<string, string>> = {{"]
    # SOURCE order, not sorted. Python dicts preserve insertion order and
    # `chiptime codes` prints them in it, so sorting here would make the CLI's
    # output diverge -- which is exactly how it was caught. Source order is just as
    # deterministic; it is the declaration order in errors.py.
    for key, value in mapping.items():
        lines.append(f"  {json.dumps(key)}: {json.dumps(value)},")
    lines.append("};")
    return "\n".join(lines)


def defect_map() -> str:
    lines = [
        "\n/** Defect code to the `FitError` subclass it raises as in strict mode. */",
        "export const DEFECT_ERROR_KIND: Readonly<Record<string, ErrorKind>> = {",
    ]
    for code in sorted(_DEFECT_ERROR_CLASS):
        lines.append(f"  {json.dumps(code)}: {json.dumps(_DEFECT_ERROR_CLASS[code].__name__)},")
    lines.append("};")
    return "\n".join(lines)


def main() -> None:
    body = (
        HEADER
        + table("ERROR_CODES", ERROR_CODES, "Fatal and collected error codes (contract #5).")
        + table("WARNING_CODES", WARNING_CODES, "Non-fatal observations surfaced in `warnings[]`.")
        + table(
            "PROVENANCE_CODES",
            PROVENANCE_CODES,
            "Every drop, repair, synthesis and reinterpretation (contract #1).",
        )
        + defect_map()
        + "\n"
    )
    OUT.write_text(body, encoding="utf-8")
    counts = (
        f"{len(ERROR_CODES)} error, {len(WARNING_CODES)} warning, "
        f"{len(PROVENANCE_CODES)} provenance"
    )
    print(f"wrote {OUT.relative_to(pathlib.Path.cwd())} ({counts})")


if __name__ == "__main__":
    main()
