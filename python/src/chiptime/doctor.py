"""Why won't this file upload, and what should I run? (F29)

The most persistent unanswered question in the FIT world is not "is my file
broken" — it is *"I fixed it and the platform still refuses it, and nothing
tells me why."* chiptime already knows the answer: it validates against
platform profiles and it has verbs that repair and edit. What was missing is
the join — a single command that reads a stubborn file and prints what is
wrong, who cares, and **the exact command that fixes it**.

That is the "errors are written for agents" contract (code + sentence +
suggested flag) applied to a whole file, for humans.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import chiptime
from chiptime.validate import Finding, Platform, validate

Source = Any


@dataclass(frozen=True, slots=True)
class Remedy:
    """A concrete next step, not a hint.

    Attributes:
        command: The command to run, ready to paste.
        reason: Why this fixes the findings it covers.
        codes: The finding codes this remedy resolves.
        priority: Lower runs first (structural repair before cosmetics).
    """

    command: str
    reason: str
    codes: tuple[str, ...]
    priority: int = 50


@dataclass(slots=True)
class Diagnosis:
    """What a platform will make of this file, and what to do about it.

    Attributes:
        platform: The profile the verdict is against.
        will_upload: True when nothing blocking was found.
        blocking: Findings that will cause rejection.
        advisory: Findings worth knowing that should not block.
        remedies: Ordered, deduplicated next steps.
        unresolved: Blocking findings with no known automatic fix.
        summary: One-line description of the parse itself.
    """

    platform: str
    will_upload: bool
    blocking: list[Finding] = field(default_factory=list)
    advisory: list[Finding] = field(default_factory=list)
    remedies: list[Remedy] = field(default_factory=list)
    unresolved: list[Finding] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "platform": self.platform,
            "will_upload": self.will_upload,
            "blocking": [{"code": f.code, "detail": f.detail} for f in self.blocking],
            "advisory": [{"code": f.code, "detail": f.detail} for f in self.advisory],
            "remedies": [
                {"command": r.command, "reason": r.reason, "codes": list(r.codes)}
                for r in self.remedies
            ],
            "unresolved": [{"code": f.code, "detail": f.detail} for f in self.unresolved],
            "summary": self.summary,
        }


# Finding code → how to fix it. Deliberately small: a remedy table that
# prescribes something which does not work is worse than saying "I don't
# know", so every entry here is exercised by a test that runs the command
# and re-validates.
_REPAIR_CODES = (
    "VAL_GC_NO_SESSION",
    "VAL_GC_NO_ACTIVITY",
    "VAL_GC_NO_LAP",
    "VAL_GC_NO_FILE_ID",
    "VAL_GC_NO_TIME_CREATED",
    "VAL_GC_NO_MANUFACTURER",
    "VAL_GC_NO_EVENTS",
    "VAL_GC_NO_TIMER_STOP",
    "VAL_GC_LOCAL_TIMESTAMP",
    "VAL_GC_NONMONOTONIC_SOURCE",
    "VAL_STRAVA_NO_SESSION",
    "VAL_STRAVA_NO_RECORDS",
    "VAL_SPEC_NO_FILE_ID",
)


def _remedies_for(codes: set[str], src_name: str) -> tuple[list[Remedy], set[str]]:
    """Map findings to commands; return the remedies and the codes covered."""
    remedies: list[Remedy] = []
    covered: set[str] = set()

    repairable = sorted(codes & set(_REPAIR_CODES))
    if repairable:
        remedies.append(
            Remedy(
                command=f"chiptime repair {src_name} -o fixed.fit",
                reason=(
                    "rebuilds the structure platforms require (file identity, timer events, "
                    "session/lap/activity summaries) from the data that is actually there"
                ),
                codes=tuple(repairable),
                priority=10,
            )
        )
        covered |= set(repairable)

    if "VAL_GC_NOT_ACTIVITY" in codes:
        remedies.append(
            Remedy(
                command=f"chiptime parse {src_name}",
                reason=(
                    "this is not an activity file, so an activity upload will never accept it; "
                    "check what it actually is"
                ),
                codes=("VAL_GC_NOT_ACTIVITY",),
                priority=20,
            )
        )
        covered.add("VAL_GC_NOT_ACTIVITY")

    if "VAL_GC_CORRUPTION_GAPS" in codes:
        remedies.append(
            Remedy(
                command=f"chiptime repair {src_name} -o fixed.fit --mode forensic",
                reason=(
                    "the file has corruption gaps; forensic salvage recovers the most it can "
                    "and records exactly what was skipped"
                ),
                codes=("VAL_GC_CORRUPTION_GAPS",),
                priority=15,
            )
        )
        covered.add("VAL_GC_CORRUPTION_GAPS")

    remedies.sort(key=lambda r: (r.priority, r.command))
    return remedies, covered


def doctor(
    src: Source,
    *,
    platform: Platform = "garmin-connect",
    mode: chiptime.Mode = "lenient",
) -> Diagnosis:
    """Diagnose why a platform will refuse a file, and prescribe the fix.

    Args:
        src: Path, bytes, or binary file object.
        platform: Which platform's observed rules to judge against.
        mode: Parse policy for reading the input.

    Returns:
        `Diagnosis` with blocking findings, advisory findings, ordered
        remedies, and any blocking finding for which chiptime has no
        automatic fix (named honestly rather than papered over).
    """
    parsed = chiptime.parse(src, mode=mode)
    findings = validate(src, platform=platform)
    blocking = [f for f in findings if f.level == "error"]
    advisory = [f for f in findings if f.level != "error"]

    name = src if isinstance(src, str) else "FILE"
    remedies, covered = _remedies_for({f.code for f in findings}, str(name))
    unresolved = [f for f in blocking if f.code not in covered]

    bits = [f"parse {'ok' if parsed.ok else 'FAILED'}"]
    activity = parsed.activity
    if activity is not None and activity.sessions:
        session = activity.sessions[0]
        bits.append(f"{session.records.n} records")
        if session.derived.distance_m:
            bits.append(f"{session.derived.distance_m / 1000:.2f} km")
        if session.discrepancies:
            bits.append(f"{len(session.discrepancies)} declared-vs-derived discrepancies")
    if parsed.recovery is not None:
        bits.append(f"{parsed.recovery.recovered_records} messages recovered")

    return Diagnosis(
        platform=str(platform),
        will_upload=not blocking,
        blocking=blocking,
        advisory=advisory,
        remedies=remedies,
        unresolved=unresolved,
        summary=" · ".join(bits),
    )
