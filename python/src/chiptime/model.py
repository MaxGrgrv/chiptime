"""The canonical semantic model (PRD §7): Activity → Sessions → Laps/Records.

Structural invariants:
- Stream.values: None means ABSENT (sentinel or dropout); 0 is a real zero
  (taxonomy #64). Streams are independently sparse (#68).
- Lap/Session end times derive from start_time + total_elapsed_time, never
  from the summary message's write-timestamp (taxonomy #50).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Stream:
    """One column of record data — every FIT record field becomes a stream.

    The honesty rule lives here: in `values`, ``None`` means the sensor said
    *nothing* (dropout, sentinel on the wire) and ``0`` means it said *zero*
    (coasting). They are never conflated, so a wire sentinel can never leak
    into an average.

    Attributes:
        name: Stream name — the FIT field name, or a promoted developer-field
            name like ``stryd_power``.
        units: Unit string from the profile (``"bpm"``, ``"m/s"``), if known.
        values: One entry per record, index-aligned with ``Records.time``.
        source: ``"native"`` for profile fields, ``"developer:<vendor>"`` or
            ``"developer"`` for developer fields.
    """

    name: str
    units: str | None
    values: list[Any]  # int | float | str | None per record
    source: str = "native"  # native | developer:<vendor> | developer

    @property
    def present_count(self) -> int:
        return sum(1 for v in self.values if v is not None)


@dataclass(slots=True)
class Records:
    """The per-second timeline, stored as columns rather than rows.

    One shared ``time`` axis plus one `Stream` per field that ever appeared
    in a record — lossless (unknown fields become streams too) and
    analytics-friendly. Row-oriented access is a view (`rows`), not the
    storage.

    Attributes:
        time: Record timestamps (``None`` where a record carried no time).
        streams: Stream name → `Stream`, index-aligned with ``time``.
    """

    time: list[datetime | None] = field(default_factory=list)
    streams: dict[str, Stream] = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.time)

    def stream(self, name: str) -> Stream | None:
        return self.streams.get(name)

    def rows(self) -> Iterator[dict[str, Any]]:
        for i, t in enumerate(self.time):
            row: dict[str, Any] = {"time": t}
            for name, s in self.streams.items():
                row[name] = s.values[i]
            yield row

    def to_pandas(self) -> Any:
        """DataFrame view (requires the `chiptime[pandas]` extra). None stays
        NaN/NA — never silently zero (taxonomy #64)."""
        try:
            import pandas as pd  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - env-dependent
            raise ImportError(
                "pandas is not installed; use `pip install chiptime[pandas]`"
            ) from exc
        data: dict[str, Any] = {"time": self.time}
        for name, s in self.streams.items():
            data[name] = s.values
        return pd.DataFrame(data)


@dataclass(slots=True)
class Totals:
    """One set of summary numbers for a session or lap.

    Appears twice on a `Session` — ``declared`` (the device's claim, absent
    if the message never arrived) and ``derived`` (recomputed from the
    records). Keeping both is the point: devices lie, and the disagreement
    is signal (see `Discrepancy`).

    Attributes:
        elapsed_time_s: Wall-clock span, pauses included.
        timer_time_s: Time with the timer running.
        moving_time_s: Time actually moving (derived only).
        distance_m: Distance in meters.
        ascent_m: Total climb in meters.
        descent_m: Total descent in meters.
        calories_kcal: Energy as reported.
        avg: Mean per stream name (``{"power": 187.0, ...}``).
        max: Maximum per stream name.
    """

    elapsed_time_s: float | None = None
    timer_time_s: float | None = None
    moving_time_s: float | None = None
    distance_m: float | None = None
    ascent_m: float | None = None
    descent_m: float | None = None
    calories_kcal: float | None = None
    avg: dict[str, float] = field(default_factory=dict)
    max: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class Lap:
    """One declared lap. ``end_time`` is always start + elapsed — never the
    message's write timestamp, which devices emit late (taxonomy #50).

    Analytics note: whether a lap was a button press or an auto-lap lives in
    the raw lap message (``lap_trigger``), read by
    `chiptime.metrics.intervals.detect_structure` — pass ``result.messages``.
    """

    message_index: int | None
    start_time: datetime | None
    end_time: datetime | None  # start + elapsed (#50), never write-ts
    declared: Totals | None
    sport: str | None = None


@dataclass(slots=True)
class Length:
    """One pool length — the atom of swim structure. ``length_type`` is
    ``"active"`` for swum lengths and ``"idle"`` for wall rest; zero-length
    wall artifacts are flagged during reconciliation, not silently dropped.
    """

    start_time: datetime | None
    end_time: datetime | None
    length_type: str | None
    swim_stroke: str | None
    total_strokes: int | None
    total_elapsed_time_s: float | None


@dataclass(slots=True)
class Gap:
    """A hole in the recording, classified with evidence — an auto-pause is
    not corruption, and the ``kind`` says which is which.

    Attributes:
        start: Last good timestamp before the hole.
        end: First timestamp after it.
        duration_s: Length of the hole in seconds.
        kind: ``smart_recording | auto_pause | manual_stop | post_timer |
            corruption | unknown``.
        evidence: Human-readable reason this classification was chosen.
    """

    start: datetime
    end: datetime
    duration_s: float
    kind: str  # smart_recording|auto_pause|manual_stop|post_timer|corruption|unknown
    evidence: str


@dataclass(slots=True)
class Discrepancy:
    """A disagreement between what the device declared and what the records
    prove — surfaced, never silently reconciled.

    Attributes:
        field: Totals field name (``"distance_m"``, ...).
        declared: The device's number.
        derived: The recomputed number.
        delta: ``derived - declared``.
    """

    field: str
    declared: float
    derived: float
    delta: float


@dataclass(slots=True)
class Session:
    """One continuous bout of one sport — the center of the model.

    A workout has one session per sport segment (a triathlon has five:
    swim, transition, bike, transition, run). Everything hangs off it:
    per-second data (``records``), declared structure (``laps``,
    ``lengths``), and the declared-vs-derived totals pair.

    Attributes:
        sport: FIT sport name (``"running"``, ``"cycling"``, ...).
        sub_sport: Refinement (``"lap_swimming"``, ``"open_water"``, ...).
        start_time: Session start.
        end_time: Start + declared elapsed when known.
        laps: Declared laps in order.
        lengths: Pool lengths (swims only).
        records: The per-second timeline.
        declared: The device's totals, if its session message survived.
        derived: Totals recomputed from the records — always present.
        discrepancies: Where declared and derived disagree materially.
        rebuilt: True when no session message survived and this one was
            synthesized from the records (recorded in provenance).
    """

    sport: str
    sub_sport: str | None
    start_time: datetime | None
    end_time: datetime | None  # start + declared elapsed when known
    laps: list[Lap] = field(default_factory=list)
    lengths: list[Length] = field(default_factory=list)
    records: Records = field(default_factory=Records)
    declared: Totals | None = None
    derived: Totals = field(default_factory=Totals)
    discrepancies: list[Discrepancy] = field(default_factory=list)
    rebuilt: bool = False  # True when synthesized from records (#95, F9)


@dataclass(slots=True)
class DeviceInfo:
    """What recorded the file — manufacturer, product, firmware. Vendor
    quirk handling keys off this."""

    manufacturer: str | int | None = None
    product: int | None = None
    product_name: str | None = None
    serial_number: int | None = None
    software_version: float | None = None


@dataclass(slots=True)
class AthleteProfile:
    friendly_name: str | None = None
    gender: str | None = None
    age: int | None = None
    weight_kg: float | None = None
    height_m: float | None = None


@dataclass(slots=True)
class Event:
    time: datetime | None
    event: str | int | None
    event_type: str | int | None
    data: int | None = None


@dataclass(slots=True)
class Activity:
    """The whole workout: every session plus file-level context.

    Attributes:
        sessions: One per sport bout, in order (multisport gives several).
        events: Timer and device events (start/stop/battery/...).
        gaps: Recording holes across the timeline, each classified.
        device: Recording device identity, when the file says.
        athlete: Athlete profile fields, when present.
        local_timestamp: Raw local-time string from the activity message.
        utc_offset_s: Validated local-UTC offset (ADR-0005), or None.
        hrv_intervals_s: Beat-to-beat RR intervals when the file logged HRV.
    """

    sessions: list[Session] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    gaps: list[Gap] = field(default_factory=list)  # classified in F8
    device: DeviceInfo | None = None
    athlete: AthleteProfile | None = None
    local_timestamp: str | None = None  # from activity message
    utc_offset_s: int | None = None  # validated local-UTC offset (ADR-0005 §4)
    hrv_intervals_s: list[float] = field(default_factory=list)  # RR intervals (#72)
