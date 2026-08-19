"""Zone resolution ladder (ADR-0008 §4): explicit settings > in-file zone
messages > absent. Never estimated from the workout itself."""

from __future__ import annotations

from chiptime.message import Message
from chiptime.metrics.settings import AthleteSettings


def _bounds_from_messages(
    messages: list[Message] | None, msg_name: str, field: str
) -> tuple[float, ...] | None:
    if not messages:
        return None
    indexed: list[tuple[int, float]] = []
    for m in messages:
        if m.name != msg_name:
            continue
        v = m.get(field)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            idx = m.get("message_index")
            indexed.append((idx if isinstance(idx, int) else len(indexed), float(v)))
    if not indexed:
        return None
    indexed.sort(key=lambda p: p[0])
    return tuple(v for _, v in indexed)


def hr_zone_bounds(
    settings: AthleteSettings | None,
    messages: list[Message] | None = None,
) -> tuple[tuple[float, ...] | None, str | None]:
    """Ascending upper bounds (bpm) + their basis ("settings" | "file:hr_zone")."""
    if settings is not None and settings.hr_zone_bounds:
        return settings.hr_zone_bounds, "settings"
    bounds = _bounds_from_messages(messages, "hr_zone", "high_bpm")
    if bounds:
        return bounds, "file:hr_zone"
    return None, None


def power_zone_bounds(
    settings: AthleteSettings | None,
    messages: list[Message] | None = None,
) -> tuple[tuple[float, ...] | None, str | None]:
    """Ascending upper bounds (W) + their basis ("settings" | "file:power_zone")."""
    if settings is not None and settings.power_zone_bounds:
        return settings.power_zone_bounds, "settings"
    bounds = _bounds_from_messages(messages, "power_zone", "high_value")
    if bounds:
        return bounds, "file:power_zone"
    return None, None
