"""Optional analytics on chiptime's honest streams.

Import explicitly (`from chiptime import metrics`) — the core never imports
this module. Everything here inherits the streams' guarantees: sentinels are
already null, zero is real (taxonomy #64), so a 65535 W spike can never
corrupt a curve. Missing data shrinks coverage; it is never filled in.

Names are generic on purpose (no trademarked training-metric names).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from chiptime.model import Session

MEAN_MAX_MIN_COVERAGE = 0.9  # a window needs >=90% present samples
ZONE_DT_CAP_S = 30.0  # ADR-0005 gap policy reused


def mean_max(values: list[Any], windows: list[int]) -> dict[int, float | None]:
    """Best rolling average per window size, in the RECORD domain.

    At 1 Hz recording (the dominant case) record-domain == time-domain; for
    smart-recording files interpret windows as record counts. Windows with
    less than 90% data coverage return None — absence is not zero.
    """
    nums = [
        float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
        for v in values
    ]
    n = len(nums)
    prefix = [0.0]
    present = [0]
    for v in nums:
        prefix.append(prefix[-1] + (v or 0.0))
        present.append(present[-1] + (1 if v is not None else 0))
    out: dict[int, float | None] = {}
    for w in windows:
        if w <= 0 or w > n:
            out[w] = None
            continue
        best: float | None = None
        min_present = int(w * MEAN_MAX_MIN_COVERAGE + 0.999999)
        for i in range(n - w + 1):
            have = present[i + w] - present[i]
            if have < min_present:
                continue
            avg = (prefix[i + w] - prefix[i]) / have
            if best is None or avg > best:
                best = avg
        out[w] = best
    return out


def time_in_zones(
    times: list[datetime | None], values: list[Any], bounds: list[float]
) -> list[float]:
    """Seconds spent per zone. Zones: (-inf, b0], (b0, b1], ..., (bn, inf) —
    len(bounds)+1 buckets. dt attribution per record, capped at 30 s
    (a gap is a gap, not an hour in zone 2). None samples contribute nowhere."""
    zones = [0.0] * (len(bounds) + 1)
    for i in range(len(times) - 1):
        t0, t1 = times[i], times[i + 1]
        v = values[i]
        if t0 is None or t1 is None or not isinstance(v, (int, float)):
            continue
        dt = (t1 - t0).total_seconds()
        if dt <= 0:
            continue
        dt = min(dt, ZONE_DT_CAP_S)
        z = 0
        for b in bounds:
            if v > b:
                z += 1
            else:
                break
        zones[z] += dt
    return zones


def swolf(session: Session) -> tuple[list[int | None], float | None]:
    """Per-active-length SWOLF (strokes + seconds) and the mean over lengths
    where both parts are present. Pool swimming only (#73)."""
    per: list[int | None] = []
    for ln in session.lengths:
        if ln.length_type != "active":
            continue
        if ln.total_strokes is None or ln.total_elapsed_time_s is None:
            per.append(None)
            continue
        per.append(round(ln.total_strokes + ln.total_elapsed_time_s))
    known = [v for v in per if v is not None]
    return per, (sum(known) / len(known)) if known else None
