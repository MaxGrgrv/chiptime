"""What a file discloses, and how to remove it (F28).

A FIT file carries more than a route: device serial numbers, and often age,
gender, height, weight, resting/max heart rate and threshold power — beside
a GPS trace that usually begins and ends at someone's front door. People
share these files with coaches, paste them into forum threads, and attach
them to bug reports.

Two verbs, because they answer different questions:

- `reveal` — *what does this file disclose?* Read-only; writes nothing.
- `scrub`  — *remove it*, and write a file that still parses and uploads.

Both read one category table, so a report can never disagree with what the
scrubber would actually remove.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import chiptime
from chiptime.encode import encodable_from_message, encode_messages
from chiptime.errors import Diagnostic, FitError, ProvenanceEntry
from chiptime.message import FieldValue, Message
from chiptime.result import Mode, ParseResult

Source = Any

# Coordinates in a disclosure report are rounded to this many decimals
# (~1.1 km — neighbourhood, not doorstep). A report that prints your front
# door is a footgun: these reports get pasted into the same threads the
# files do.
COARSE_DECIMALS = 2

EARTH_RADIUS_M = 6_371_000.0

RECORD, LAP, SESSION = 20, 19, 18
POSITION_FIELDS = ("position_lat", "position_long")
SUMMARY_POSITION_FIELDS = (
    "start_position_lat",
    "start_position_long",
    "end_position_lat",
    "end_position_long",
    "nec_lat",
    "nec_long",
    "swc_lat",
    "swc_long",
)


class ScrubError(FitError):
    """A scrub cannot be performed; no bytes are written."""


@dataclass(frozen=True, slots=True)
class Category:
    """A class of personal data: whole messages to drop, fields to null.

    `field_scope` matters more than it looks. `session.max_heart_rate` is the
    highest heart rate *reached during that workout* — real training data.
    `zones_target.max_heart_rate` is the athlete's configured physiological
    maximum — personal. Same field name, opposite meaning, so fields are only
    treated as personal inside the messages named here. An empty scope means
    the field is personal wherever it appears (a serial number always is).
    """

    key: str
    label: str
    messages: frozenset[str]
    fields: frozenset[str]
    field_scope: frozenset[str] = frozenset()


CATEGORIES: tuple[Category, ...] = (
    Category(
        "identity",
        "who you are",
        frozenset({"user_profile"}),
        frozenset({"friendly_name", "gender", "age", "height", "weight", "global_id"}),
        field_scope=frozenset({"user_profile", "athlete", "workout"}),
    ),
    Category(
        "serials",
        "which device this is",
        frozenset(),
        frozenset({"serial_number", "ant_device_number"}),
    ),
    Category(
        "body_metrics",
        "your physiology",
        frozenset({"zones_target"}),
        frozenset(
            {
                "functional_threshold_power",
                "threshold_heart_rate",
                "max_heart_rate",
                "resting_heart_rate",
                "default_max_heart_rate",
                "default_max_running_heart_rate",
                "default_max_biking_heart_rate",
                "vo2_max",
            }
        ),
        field_scope=frozenset({"user_profile", "zones_target", "hrv", "max_met_data"}),
    ),
)
CATEGORY_KEYS = tuple(c.key for c in CATEGORIES)


@dataclass(frozen=True, slots=True)
class PrivacyFinding:
    """One thing the file discloses."""

    category: str
    message: str
    field: str | None
    count: int
    detail: str


@dataclass(slots=True)
class PrivacyReport:
    """What a file discloses, by category.

    Coordinates are deliberately coarse (see `COARSE_DECIMALS`).

    Attributes:
        findings: One entry per disclosing message/field, with counts.
        positions_present: Records carrying GPS coordinates.
        start_coarse: Approximate start coordinate, rounded, or None.
        end_coarse: Approximate end coordinate, rounded, or None.
        clean_categories: Categories this file does not disclose at all.
    """

    findings: list[PrivacyFinding] = field(default_factory=list)
    positions_present: int = 0
    start_coarse: tuple[float, float] | None = None
    end_coarse: tuple[float, float] | None = None
    clean_categories: list[str] = field(default_factory=list)

    @property
    def discloses_location(self) -> bool:
        return self.positions_present > 0 or self.start_coarse is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [
                {
                    "category": f.category,
                    "message": f.message,
                    "field": f.field,
                    "count": f.count,
                    "detail": f.detail,
                }
                for f in self.findings
            ],
            "positions_present": self.positions_present,
            "start_coarse": list(self.start_coarse) if self.start_coarse else None,
            "end_coarse": list(self.end_coarse) if self.end_coarse else None,
            "clean_categories": self.clean_categories,
        }


@dataclass(slots=True)
class ScrubResult:
    """The scrubbed file plus an account of what was removed.

    Attributes:
        data: The scrubbed ``.fit`` bytes.
        provenance: One entry per category removed, with counts.
        warnings: Non-fatal observations (e.g. every position was concealed).
        removed: Count of removals per category key.
        output_strict_ok: Self-check — the output re-parsed in strict mode.
        parse_result: The parse of the *input*, for inspection.
    """

    data: bytes
    provenance: list[ProvenanceEntry] = field(default_factory=list)
    warnings: list[Diagnostic] = field(default_factory=list)
    removed: dict[str, int] = field(default_factory=dict)
    output_strict_ok: bool = False
    parse_result: ParseResult | None = None


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _position(m: Message) -> tuple[float, float] | None:
    lat, lon = (_num(m.get(f)) for f in POSITION_FIELDS)
    return (lat, lon) if lat is not None and lon is not None else None


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(a[0]), math.radians(a[1])
    lat2, lon2 = math.radians(b[0]), math.radians(b[1])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, h)))


def _coarse(p: tuple[float, float] | None) -> tuple[float, float] | None:
    return (round(p[0], COARSE_DECIMALS), round(p[1], COARSE_DECIMALS)) if p else None


def reveal(src: Source, *, mode: Mode = "lenient") -> PrivacyReport:
    """Report what a file discloses about you. Reads only; writes nothing.

    Args:
        src: Path, bytes, or binary file object.
        mode: Parse policy for reading the input.

    Returns:
        `PrivacyReport`. Coordinates are rounded to ~1.1 km so the report
        itself is safe to share — which is the whole point of having one.
    """
    parsed = chiptime.parse(src, mode=mode)
    report = PrivacyReport()
    counts: dict[tuple[str, str, str | None], int] = {}
    key: tuple[str, str, str | None]
    positions: list[tuple[float, float]] = []

    for m in parsed.messages:
        pos = _position(m)
        if pos is not None and m.global_num == RECORD:
            positions.append(pos)
        for cat in CATEGORIES:
            if m.name in cat.messages:
                key = (cat.key, m.name, None)
                counts[key] = counts.get(key, 0) + 1
                continue
            if cat.field_scope and m.name not in cat.field_scope:
                continue
            for fname, fv in m.fields.items():
                if fname in cat.fields and fv.value is not None:
                    key = (cat.key, m.name, fname)
                    counts[key] = counts.get(key, 0) + 1
        if m.global_num in (LAP, SESSION):
            for pos_field in SUMMARY_POSITION_FIELDS:
                summary_fv = m.fields.get(pos_field)
                if summary_fv is not None and summary_fv.value is not None:
                    key = ("location", m.name, pos_field)
                    counts[key] = counts.get(key, 0) + 1

    for entry_key, count in sorted(
        counts.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2] or "")
    ):
        cat_key, msg, found_field = entry_key
        detail = (
            f"{msg} message present ({count} time(s))"
            if found_field is None
            else f"{msg}.{found_field} present in {count} message(s)"
        )
        report.findings.append(PrivacyFinding(cat_key, msg, found_field, count, detail))

    report.positions_present = len(positions)
    if positions:
        report.start_coarse = _coarse(positions[0])
        report.end_coarse = _coarse(positions[-1])
        report.findings.append(
            PrivacyFinding(
                "location",
                "record",
                "position_lat/long",
                len(positions),
                f"{len(positions)} GPS points; the route starts and ends at real places",
            )
        )

    disclosed = {f.category for f in report.findings}
    report.clean_categories = [k for k in (*CATEGORY_KEYS, "location") if k not in disclosed]
    return report


def _null_fields(m: Message, names: tuple[str, ...] | frozenset[str]) -> tuple[Message, int]:
    """Null the named fields (FIT *invalid*, never zero — contract #4)."""
    import dataclasses

    fields = dict(m.fields)
    hit = 0
    for name in names:
        fv = fields.get(name)
        if fv is not None and fv.value is not None:
            fields[name] = FieldValue(None, None, fv.units)
            hit += 1
    return (dataclasses.replace(m, fields=fields), hit) if hit else (m, 0)


def scrub(
    src: Source,
    *,
    identity: bool = True,
    serials: bool = True,
    body_metrics: bool = True,
    gps_radius_m: float | None = None,
    drop_all_gps: bool = False,
    mode: Mode = "lenient",
) -> ScrubResult:
    """Remove personal data and write a file that still parses and uploads.

    Metadata categories are on by default because removing them costs no
    measurements. Location scrubbing is opt-in and explicit, because it does.

    Args:
        src: Path, bytes, or binary file object.
        identity: Drop `user_profile` and identity fields.
        serials: Null device serial numbers and ANT device ids.
        body_metrics: Drop `zones_target` and physiology fields (FTP, max HR,
            VO2max…).
        gps_radius_m: Conceal every GPS point within this many metres of the
            route's **first or last** fix — wherever it occurs in the ride,
            so a loop that passes home mid-route is covered too.
        drop_all_gps: Remove every coordinate outright.
        mode: Parse policy for reading the input.

    Returns:
        `ScrubResult` with the scrubbed bytes, provenance, per-category
        counts, and the strict-mode self-check verdict.

    Raises:
        ScrubError: nothing was selected to remove.
    """
    if not any((identity, serials, body_metrics, gps_radius_m, drop_all_gps)):
        raise ScrubError(
            "SCRUB_NOTHING_SELECTED",
            "scrub() was called with every category disabled",
            suggestion="enable a category, or pass gps_radius_m= to conceal locations",
        )

    parsed = chiptime.parse(src, mode=mode)
    enabled = {
        "identity": identity,
        "serials": serials,
        "body_metrics": body_metrics,
    }
    drop_messages = {name for cat in CATEGORIES if enabled[cat.key] for name in cat.messages}
    null_fields = frozenset(name for cat in CATEGORIES if enabled[cat.key] for name in cat.fields)

    anchors: list[tuple[float, float]] = []
    if gps_radius_m and not drop_all_gps:
        fixes = [
            p for m in parsed.messages if m.global_num == RECORD and (p := _position(m)) is not None
        ]
        if fixes:
            anchors = [fixes[0], fixes[-1]]

    kept: list[Message] = []
    removed: dict[str, int] = dict.fromkeys((*CATEGORY_KEYS, "location"), 0)
    positions_seen = 0

    for m in parsed.messages:
        if m.name in drop_messages:
            for cat in CATEGORIES:
                if m.name in cat.messages:
                    removed[cat.key] += 1
            continue
        new = m
        for cat in CATEGORIES:
            if not enabled[cat.key]:
                continue
            if cat.field_scope and new.name not in cat.field_scope:
                continue  # same field name, different meaning — see Category.field_scope
            new, hit = _null_fields(new, cat.fields & null_fields)
            removed[cat.key] += hit
        if new.global_num == RECORD:
            pos = _position(new)
            if pos is not None:
                positions_seen += 1
                conceal = drop_all_gps or (
                    bool(anchors)
                    and gps_radius_m is not None
                    and min(_haversine_m(pos, a) for a in anchors) <= gps_radius_m
                )
                if conceal:
                    new, hit = _null_fields(new, POSITION_FIELDS)
                    removed["location"] += bool(hit)
        elif new.global_num in (LAP, SESSION) and (drop_all_gps or gps_radius_m):
            new, hit = _null_fields(new, SUMMARY_POSITION_FIELDS)
            removed["location"] += hit
        kept.append(new)

    prov: list[ProvenanceEntry] = []
    codes = {
        "identity": "PII_IDENTITY_REMOVED",
        "serials": "PII_SERIALS_REMOVED",
        "body_metrics": "PII_BODY_METRICS_REMOVED",
        "location": "PII_LOCATION_CONCEALED",
    }
    for key, count in removed.items():
        if count:
            prov.append(
                ProvenanceEntry(
                    code=codes[key],
                    action="dropped",
                    scope="file",
                    detail=f"removed {count} {key.replace('_', ' ')} item(s) at the user's request",
                    data={"category": key, "count": count},
                )
            )

    warnings: list[Diagnostic] = []
    if positions_seen and removed["location"] >= positions_seen:
        warnings.append(
            Diagnostic(
                code="SCRUB_ALL_POSITIONS_CONCEALED",
                detail=(
                    f"every one of the {positions_seen} GPS points fell inside the "
                    "concealment radius; the output has no route at all"
                ),
                scope="file",
            )
        )

    data = encode_messages([encodable_from_message(m) for m in kept])
    try:
        chiptime.parse(data, mode="strict")
        strict_ok = True
    except FitError:
        strict_ok = False
    return ScrubResult(
        data=data,
        provenance=prov,
        warnings=warnings,
        removed={k: v for k, v in removed.items() if v},
        output_strict_ok=strict_ok,
        parse_result=parsed,
    )
