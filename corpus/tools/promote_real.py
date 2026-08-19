#!/usr/bin/env python3
"""Promote a real device file into the PRIVATE corpus tier (ADR-0007).

Usage:
    uv run --project python python corpus/tools/promote_real.py \
        ~/Downloads/ride.fit real/wahoo-roam-ride --note "..."

Writes corpus/private/cases/<category>/<slug>/{input.fit,case.json,expected.json}
and updates corpus/private/MANIFEST.json. The private tier is git-ignored;
nothing here may ever be committed (coordinates are a home address).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
CORPUS = TOOLS.parent
sys.path.insert(0, str(CORPUS.parent / "python" / "src"))

import chiptime


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("dest", help="category/slug, e.g. real/wahoo-roam-ride")
    ap.add_argument("--note", default="")
    args = ap.parse_args()

    src = Path(args.source).expanduser()
    data = src.read_bytes()
    result = chiptime.parse(data)

    category, slug = args.dest.split("/", 1)
    d = CORPUS / "private" / "cases" / category / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "input.fit").write_bytes(data)
    grade = "reject" if not result.ok else ("partial" if result.recovery else "ok")
    case = {
        "slug": slug,
        "category": category,
        "taxonomy": [],
        "tier": "real",
        "expect": grade,
        "modes": {"strict": "unchecked", "lenient": grade, "forensic": grade},
        "build": "external",
        "input_sha256": hashlib.sha256(data).hexdigest(),
        "source": "own-archive",
        "notes": args.note or f"promoted from {src.name}",
    }
    (d / "case.json").write_text(json.dumps(case, indent=2) + "\n")
    (d / "expected.json").write_bytes(result.to_canonical_json())

    manifest_path = CORPUS / "private" / "MANIFEST.json"
    cases = []
    if manifest_path.exists():
        cases = json.loads(manifest_path.read_text())["cases"]
    rel = str(d.relative_to(CORPUS / "private"))
    if rel not in cases:
        cases.append(rel)
    manifest_path.write_text(
        json.dumps({"manifest_schema": 1, "private": True, "cases": sorted(cases)}, indent=2) + "\n"
    )
    print(
        f"promoted -> corpus/private/cases/{category}/{slug} (grade: {grade},"
        f" {len(data)} bytes, {sum(len(p.messages) for p in result.parts)} messages)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
