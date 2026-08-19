"""Gap classification (taxonomy #43/#44) per ADR-0005 §7. Never interpolates."""

from __future__ import annotations

from datetime import datetime

from chiptime.model import Event, Gap
from chiptime.semantics.timers import TimerState

GAP_MIN_S = 10.0  # below this: not worth reporting
SMART_RECORDING_MAX_S = 30.0


def classify_gaps(
    times: list[datetime | None],
    offsets: list[int],
    state: TimerState,
    events: list[Event],
    skipped_ranges: list[tuple[int, int]],
) -> list[Gap]:
    stops = [
        e
        for e in events
        if e.event == "timer" and e.event_type in ("stop", "stop_all") and e.time is not None
    ]
    final_stop = state.final_stop
    gaps: list[Gap] = []
    for i in range(len(times) - 1):
        t0, t1 = times[i], times[i + 1]
        if t0 is None or t1 is None:
            continue
        dt = (t1 - t0).total_seconds()
        if dt < GAP_MIN_S:
            continue
        gaps.append(
            _classify(
                t0, t1, dt, offsets[i], offsets[i + 1], state, stops, final_stop, skipped_ranges
            )
        )
    return gaps


def _classify(
    t0: datetime,
    t1: datetime,
    dt: float,
    off0: int,
    off1: int,
    state: TimerState,
    stops: list[Event],
    final_stop: datetime | None,
    skipped_ranges: list[tuple[int, int]],
) -> Gap:
    # corruption: the two records straddle a resynchronized byte range
    for a, b in skipped_ranges:
        if off0 < a and off1 > b:
            return Gap(
                t0,
                t1,
                dt,
                "corruption",
                f"{b - a} corrupt byte(s) were skipped between these records",
            )

    # a stop event inside the gap → deliberate pause/stop
    for e in stops:
        assert e.time is not None
        if t0 <= e.time <= t1:
            trigger = "auto" if e.data == 1 else "manual"
            kind = "auto_pause" if trigger == "auto" else "manual_stop"
            return Gap(
                t0,
                t1,
                dt,
                kind,
                f"timer {e.event_type} ({trigger}) at {e.time.strftime('%H:%M:%S')} inside the gap",
            )

    if final_stop is not None and t0 >= final_stop:
        return Gap(
            t0,
            t1,
            dt,
            "post_timer",
            "records written after the final timer stop (excluded from stats)",
        )

    if dt <= SMART_RECORDING_MAX_S:
        return Gap(
            t0,
            t1,
            dt,
            "smart_recording",
            "short event-less gap; smart recording writes only on change",
        )

    return Gap(t0, t1, dt, "unknown", f"no timer events explain this {dt:.0f}s silence")
