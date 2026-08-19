#!/usr/bin/env python3
"""Verify chiptime's hand-authored core profile against fitdecode's generated one.

ADR-0004 §2: our tables are functional interface facts written from public
knowledge; this script hard-gates their accuracy against an independent
MIT-licensed implementation. Run from repo root:

    uv run --project python --group baselines python scripts/check_profile_against_fitdecode.py

Exit 0 = every message/field/enum we declare matches fitdecode (modulo the
declared intentional divergences). Never imported by chiptime.
"""

from __future__ import annotations

import sys

from fitdecode import profile as fdp

from chiptime.profile import ENUMS, MESSAGES
from chiptime.profile.core import ENUMS as CORE_ENUMS
from chiptime.profile.core import MESSAGES as CORE_MESSAGES

# Intentional divergences: (message, field) pairs where chiptime deliberately
# differs. Positions: we scale semicircles→degrees at decode (taxonomy #27);
# fitdecode leaves raw semicircles.
SCALE_DIVERGENCES = {
    ("record", "position_lat"),
    ("record", "position_long"),
    ("session", "start_position_lat"),
    ("session", "start_position_long"),
    ("lap", "start_position_lat"),
    ("lap", "start_position_long"),
    ("lap", "end_position_lat"),
    ("lap", "end_position_long"),
}

KIND_MAP = {"bytes": "byte"}  # chiptime kind name -> fitdecode type name


def fail(msgs: list[str]) -> None:
    for m in msgs:
        print(f"MISMATCH: {m}")
    print(f"\n{len(msgs)} mismatches")
    sys.exit(1)


def main() -> None:
    problems: list[str] = []

    fd_messages = {mt.mesg_num: mt for mt in fdp.MESSAGE_TYPES.values()}

    for num, ours in CORE_MESSAGES.items():
        theirs = fd_messages.get(num)
        if theirs is None:
            problems.append(f"message {num} ({ours.name}): not in fitdecode profile")
            continue
        if theirs.name != ours.name:
            problems.append(f"message {num}: name {ours.name!r} != fitdecode {theirs.name!r}")
        their_fields = {f.def_num: f for f in theirs.fields.values()}
        for fnum, of in ours.fields.items():
            tf = their_fields.get(fnum)
            if tf is None:
                problems.append(f"{ours.name}.{of.name} (#{fnum}): not in fitdecode")
                continue
            if tf.name != of.name:
                problems.append(
                    f"{ours.name} field {fnum}: name {of.name!r} != fitdecode {tf.name!r}"
                )
            t_scale = float(tf.scale) if tf.scale else 1.0
            t_offset = float(tf.offset) if tf.offset else 0.0
            if (ours.name, of.name) not in SCALE_DIVERGENCES:
                if abs(t_scale - of.scale) > 1e-9:
                    problems.append(
                        f"{ours.name}.{of.name}: scale {of.scale} != fitdecode {t_scale}"
                    )
                if abs(t_offset - of.offset) > 1e-9:
                    problems.append(
                        f"{ours.name}.{of.name}: offset {of.offset} != fitdecode {t_offset}"
                    )
            t_type = getattr(tf.type, "name", None)
            if of.kind.startswith("enum:"):
                want = of.kind.removeprefix("enum:")
                if t_type != want:
                    problems.append(
                        f"{ours.name}.{of.name}: enum type {want!r} != fitdecode {t_type!r}"
                    )
            elif (of.kind in ("date_time", "local_date_time") and t_type != of.kind) or (
                of.kind in KIND_MAP and t_type != KIND_MAP[of.kind]
            ):
                problems.append(f"{ours.name}.{of.name}: kind {of.kind!r} != fitdecode {t_type!r}")

    fd_types = fdp.FIELD_TYPES
    for ename, values in CORE_ENUMS.items():
        ft = fd_types.get(ename)
        if ft is None:
            problems.append(f"enum {ename}: not in fitdecode FIELD_TYPES")
            continue
        for val, name in values.items():
            their = ft.enum.get(val) if ft.enum else None
            if their != name:
                problems.append(f"enum {ename}[{val}]: {name!r} != fitdecode {their!r}")

    # F18: verify the FULL merged tables against fitdecode over the
    # intersection (SDK version skew is reported, never failed).
    inter_msgs = inter_fields = skew = 0
    for num, ours in MESSAGES.items():
        theirs = fd_messages.get(num)
        if theirs is None:
            skew += 1
            continue
        inter_msgs += 1
        their_fields = {f.def_num: f for f in theirs.fields.values()}
        for fnum, of in ours.fields.items():
            tf = their_fields.get(fnum)
            if tf is None:
                skew += 1
                continue
            inter_fields += 1
            if tf.name != of.name:
                problems.append(
                    f"[generated] {ours.name} field {fnum}: {of.name!r} != fitdecode {tf.name!r}"
                )
            if of.units == "deg":  # our global semicircle divergence
                continue
            t_scale = float(tf.scale) if tf.scale and not isinstance(tf.scale, tuple) else 1.0
            if abs(t_scale - of.scale) > 1e-9 and not isinstance(tf.scale, tuple):
                problems.append(
                    f"[generated] {ours.name}.{of.name}: scale {of.scale} != fitdecode {t_scale}"
                )

    if problems:
        fail(problems)
    n_fields = sum(len(m.fields) for m in MESSAGES.values())
    n_enum_vals = sum(len(v) for v in ENUMS.values())
    print(
        f"ok: core verified; merged {len(MESSAGES)} messages / {n_fields} fields /"
        f" {len(ENUMS)} enums ({n_enum_vals} values)"
    )
    print(
        f"    full-profile intersection vs fitdecode: {inter_msgs} messages,"
        f" {inter_fields} fields identical; {skew} version-skew entries skipped"
    )


if __name__ == "__main__":
    main()
