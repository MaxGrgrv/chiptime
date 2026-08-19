"""Timer state machine (taxonomy #45) and the three durations (#46).

Defensive by design: unbalanced events are tolerated and recorded, never
fatal. Policies per ADR-0005 §5-§6.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from chiptime.errors import Diagnostic, ProvenanceEntry
from chiptime.model import Event

MOVING_SPEED_FLOOR = 0.1  # m/s: below this a rider/runner is stationary
MOVING_DT_CAP = 30.0  # s: one record never contributes more than this


@dataclass(slots=True)
class TimerState:
    intervals: list[tuple[datetime, datetime]]
    synthesized_final_stop: bool
    stop_without_start: bool

    def running_at(self, t: datetime) -> bool:
        return any(a <= t <= b for a, b in self.intervals)

    @property
    def final_stop(self) -> datetime | None:
        return self.intervals[-1][1] if self.intervals else None

    def timer_seconds(self) -> float | None:
        if not self.intervals:
            return None
        return sum((b - a).total_seconds() for a, b in self.intervals)


def build_timer_state(
    events: list[Event],
    first_record: datetime | None,
    last_record: datetime | None,
    warnings: list[Diagnostic],
    provenance: list[ProvenanceEntry],
    scope: str,
) -> TimerState:
    starts_stops = [
        (e.time, e.event_type)
        for e in events
        if e.event == "timer"
        and e.time is not None
        and e.event_type in ("start", "stop", "stop_all", "stop_disable_all")
    ]
    intervals: list[tuple[datetime, datetime]] = []
    open_start: datetime | None = None
    stop_without_start = False
    for t, kind in starts_stops:
        assert t is not None
        if kind == "start":
            if open_start is None:
                open_start = t
            # start-while-running: ignore (consecutive starts seen in the wild)
        else:
            if open_start is None:
                # Stop without start (#45): interval opened at first record.
                stop_without_start = True
                anchor = first_record or t
                warnings.append(
                    Diagnostic(
                        "TIMER_STOP_WITHOUT_START",
                        "timer stop event with no preceding start;"
                        " interval opened at the first record",
                        scope,
                    )
                )
                open_start = anchor
            if open_start <= t:
                intervals.append((open_start, t))
            open_start = None

    synthesized = False
    if open_start is not None:
        # Missing final stop (crash class, #45): close at the last record.
        end = last_record or open_start
        if open_start <= end:
            intervals.append((open_start, end))
        synthesized = True
        provenance.append(
            ProvenanceEntry(
                "TIMER_STOP_SYNTHESIZED",
                "synthesized",
                scope,
                "no final timer stop event; timer closed at the last record",
            )
        )
    if not starts_stops and first_record and last_record:
        # No timer events at all (minimal encoders, #88 class): the record
        # span is the best available timer estimate; recorded as-is, not
        # synthesized events.
        intervals = [(first_record, last_record)]

    return TimerState(intervals, synthesized, stop_without_start)


def moving_seconds(
    times: list[datetime | None],
    speeds: list[object] | None,
    state: TimerState,
) -> float | None:
    """ADR-0005 §6: speed-gated moving time; None without a speed stream."""
    if speeds is None:
        return None
    total = 0.0
    for i in range(len(times) - 1):
        t0, t1 = times[i], times[i + 1]
        if t0 is None or t1 is None:
            continue
        v = speeds[i]
        if not isinstance(v, (int, float)) or v <= MOVING_SPEED_FLOOR:
            continue
        if not state.running_at(t0):
            continue
        dt = (t1 - t0).total_seconds()
        if dt > 0:
            total += min(dt, MOVING_DT_CAP)
    return total
