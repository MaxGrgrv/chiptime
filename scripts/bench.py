#!/usr/bin/env python3
"""Decode benchmark on a synthetic ~1 MB ride (40k records, value-bounded).

Usage: uv run --project python python scripts/bench.py [--profile]
Informational only — never a CI gate (runner variance).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "corpus" / "tools"))

import build_fit

import chiptime


def bench_file(n: int = 40000) -> bytes:
    b = build_fit.FitBuilder()
    t0 = build_fit.fit_ts(build_fit.T0)
    b.define(0, build_fit.FILE_ID, [(0, "enum", 1), (1, "uint16", 1), (4, "uint32", 1)])
    b.data(0, 4, 1, t0)
    b.define(
        4, build_fit.EVENT, [(253, "uint32", 1), (0, "enum", 1), (1, "enum", 1), (3, "uint32", 1)]
    )
    b.data(4, t0, 0, 0, 0)
    b.define(1, build_fit.RECORD, build_fit.RECORD_FIELDS_FULL)
    lat0, lon0 = build_fit.semicircles(52.37), build_fit.semicircles(4.89)
    dist = 0
    for i in range(n):
        alt = (10 + (i % 200) + 500) * 5
        dist += 833
        b.data(
            1,
            t0 + i,
            lat0 + i * 12,
            lon0 + i * 4,
            alt,
            120 + (i % 60),
            85,
            dist,
            8333,
            180 + (i % 80),
            21,
        )
    b.data(4, t0 + n, 0, 4, 0)
    return b.build()


def main() -> int:
    data = bench_file()
    sys.stdout.write(f"bench file: {len(data) / 1e6:.2f} MB, 40k records\n")
    best = 1e9
    for _ in range(3):
        t0 = time.perf_counter()
        result = chiptime.parse(data)
        best = min(best, time.perf_counter() - t0)
    msgs = sum(len(p.messages) for p in result.parts)
    sys.stdout.write(
        f"parse: {best * 1000:.0f} ms  |  {len(data) / 1e6 / best:.2f} MB/s"
        f"  |  {msgs / best / 1000:.0f}k msgs/s\n"
    )
    if "--profile" in sys.argv:
        import cProfile
        import pstats

        pr = cProfile.Profile()
        pr.enable()
        chiptime.parse(data)
        pr.disable()
        pstats.Stats(pr).sort_stats("tottime").print_stats(15)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
