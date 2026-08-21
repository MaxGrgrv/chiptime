"""chiptime CLI — agent-first exit codes and machine-readable output.

Exit codes (stable contract, see docs/for-agents.md):
  0   parsed clean (warnings allowed)
  2   parsed with recovery/data loss — details in provenance
  3   unusable input (structurally FIT but nothing salvageable)
  4   not a FIT file at all
  64  usage error
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

import chiptime
from chiptime.errors import ERROR_CODES, PROVENANCE_CODES, WARNING_CODES
from chiptime.frames import CrcFrame, DataFrame, DefinitionFrame, FileHeader, SkippedBytes


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Any:  # exit 64, not argparse's default 2
        self.print_usage(sys.stderr)
        print(f"error: {message}", file=sys.stderr)
        raise SystemExit(64)


def main(argv: list[str] | None = None) -> int:
    ap = _Parser(prog="chiptime", description="Recovery-grade FIT file processing.")
    sub = ap.add_subparsers(dest="command", required=True)

    p_parse = sub.add_parser("parse", help="parse a FIT file")
    p_parse.add_argument("file")
    p_parse.add_argument("--mode", choices=["strict", "lenient", "forensic"], default="lenient")
    p_parse.add_argument(
        "--json", action="store_true", help="emit canonical JSON (RFC 8785) instead of a summary"
    )
    p_parse.add_argument("-o", "--output", help="write JSON to a file")
    p_parse.add_argument("--strip-pii", action="store_true")
    p_parse.add_argument("--include-raw", action="store_true")
    p_parse.add_argument(
        "--no-unknown", action="store_true", help="omit unknown messages from output"
    )

    p_inspect = sub.add_parser("inspect", help="wire-level frame table (forensics)")
    p_inspect.add_argument("file")
    p_inspect.add_argument("--limit", type=int, default=50)

    p_repair = sub.add_parser("repair", help="salvage + synthesize + write a valid .fit")
    p_repair.add_argument("file")
    p_repair.add_argument("-o", "--output", required=True)
    p_repair.add_argument("--mode", choices=["lenient", "forensic"], default="lenient")

    p_val = sub.add_parser("validate", help="check platform acceptance (heuristic)")
    p_val.add_argument("file")
    p_val.add_argument(
        "--platform", choices=["strict-spec", "garmin-connect", "strava"], default="strict-spec"
    )

    p_edit = sub.add_parser("edit", help="change what a file says about itself (metadata)")
    p_edit.add_argument("file")
    p_edit.add_argument("-o", "--output", required=True)
    p_edit.add_argument("--mode", choices=["strict", "lenient", "forensic"], default="lenient")
    p_edit.add_argument("--sport", help="new sport, e.g. running (or a raw number)")
    p_edit.add_argument("--sub-sport", dest="sub_sport", help="new sub-sport; never inferred")
    p_edit.add_argument("--manufacturer", help="new recording-device manufacturer, name or number")
    p_edit.add_argument("--product", type=int, help="new product id (numeric)")
    p_edit.add_argument(
        "--time-shift",
        dest="time_shift",
        help="signed offset applied to every timestamp: seconds, or ±HH:MM",
    )

    p_trim = sub.add_parser("trim", help="crop an activity and rebuild its totals")
    p_trim.add_argument("file")
    p_trim.add_argument("-o", "--output", required=True)
    p_trim.add_argument("--mode", choices=["strict", "lenient", "forensic"], default="lenient")
    p_trim.add_argument(
        "--after", help="keep records at/after this: ISO time, or '+5m' from the start"
    )
    p_trim.add_argument(
        "--before", help="keep records at/before this: ISO time, or '-10m' from the end"
    )

    p_an = sub.add_parser("analyze", help="per-sport workout report + insights (optional layer)")
    p_an.add_argument("file")
    p_an.add_argument("--mode", choices=["strict", "lenient", "forensic"], default="lenient")
    p_an.add_argument("--json", action="store_true", help="machine-readable report")
    p_an.add_argument("-o", "--output", help="write the report to a file")
    p_an.add_argument("--ftp", type=float, help="functional threshold power, W")
    p_an.add_argument("--max-hr", type=float, dest="max_hr")
    p_an.add_argument("--resting-hr", type=float, dest="resting_hr")
    p_an.add_argument("--sex", choices=["male", "female"], help="TRIMP coefficient")
    p_an.add_argument("--hr-zones", help="ascending bpm upper bounds, e.g. 115,135,155,172,188")
    p_an.add_argument("--power-zones", help="ascending W upper bounds")

    sub.add_parser("codes", help="print the error/warning/provenance code registry")

    args = ap.parse_args(argv)
    if args.command == "parse":
        return _cmd_parse(args)
    if args.command == "inspect":
        return _cmd_inspect(args)
    if args.command == "repair":
        return _cmd_repair(args)
    if args.command == "validate":
        return _cmd_validate(args)
    if args.command == "analyze":
        return _cmd_analyze(args)
    if args.command == "edit":
        return _cmd_edit(args)
    if args.command == "trim":
        return _cmd_trim(args)
    return _cmd_codes()


def _exit_code(result: chiptime.ParseResult) -> int:
    if any(e.code in ("NOT_FIT_FORMAT", "FIT_TOO_SMALL") for e in result.errors):
        return 4
    if not result.ok:
        return 3
    if result.recovery is not None or result.errors:
        return 2
    return 0


def _parse_bounds(raw: str | None, flag: str) -> tuple[float, ...] | None:
    if raw is None:
        return None
    try:
        bounds = tuple(float(x) for x in raw.split(","))
    except ValueError:
        print(f"error: {flag} expects comma-separated numbers", file=sys.stderr)
        raise SystemExit(64) from None
    if list(bounds) != sorted(bounds):
        print(f"error: {flag} bounds must ascend", file=sys.stderr)
        raise SystemExit(64)
    return bounds


def _parse_time_shift(raw: str | None) -> int | None:
    """Accept plain seconds or ±HH:MM (the form humans think in for timezones)."""
    if raw is None:
        return None
    text = raw.strip()
    sign = -1 if text.startswith("-") else 1
    text = text.lstrip("+-")
    try:
        if ":" in text:
            hours, minutes = text.split(":", 1)
            return sign * (int(hours) * 3600 + int(minutes) * 60)
        return sign * int(text)
    except ValueError:
        print(f"error: --time-shift expects seconds or ±HH:MM, got {raw!r}", file=sys.stderr)
        raise SystemExit(64) from None


def _cmd_edit(args: argparse.Namespace) -> int:
    shift = _parse_time_shift(args.time_shift)
    if not any((args.sport, args.sub_sport, args.manufacturer, args.product is not None, shift)):
        print("error: edit requires at least one change", file=sys.stderr)
        print(
            "suggestion: --sport / --sub-sport / --manufacturer / --product / --time-shift",
            file=sys.stderr,
        )
        return 64
    try:
        result = chiptime.edit(
            args.file,
            sport=args.sport,
            sub_sport=args.sub_sport,
            manufacturer=args.manufacturer,
            product=args.product,
            time_shift_s=shift,
            mode=args.mode,
        )
    except chiptime.NotFitError as e:
        print(f"{e.code}: {e.detail}", file=sys.stderr)
        return 4
    except chiptime.FitError as e:
        print(f"{e.code}: {e.detail}", file=sys.stderr)
        if e.suggestion:
            print(f"suggestion: {e.suggestion}", file=sys.stderr)
        return 3
    except OSError as e:
        print(f"cannot read {args.file}: {e}", file=sys.stderr)
        return 64

    with open(args.output, "wb") as f:
        f.write(result.data)
    for entry in result.provenance:
        print(f"{entry.code}: {entry.detail}")
    for warn in result.warnings:
        print(f"{warn.code}: {warn.detail}", file=sys.stderr)
    print(f"wrote {args.output} ({len(result.data)} bytes)")
    if not result.output_strict_ok:
        print(
            "warning: the edited file does not parse in strict mode; inspect before uploading",
            file=sys.stderr,
        )
        return 2
    return 0


def _cmd_trim(args: argparse.Namespace) -> int:
    if not args.after and not args.before:
        print("error: trim requires --after and/or --before", file=sys.stderr)
        print("suggestion: --after '+5m' cuts the first five minutes", file=sys.stderr)
        return 64
    try:
        result = chiptime.trim(args.file, after=args.after, before=args.before, mode=args.mode)
    except chiptime.NotFitError as e:
        print(f"{e.code}: {e.detail}", file=sys.stderr)
        return 4
    except chiptime.FitError as e:
        print(f"{e.code}: {e.detail}", file=sys.stderr)
        if e.suggestion:
            print(f"suggestion: {e.suggestion}", file=sys.stderr)
        return 3
    except OSError as e:
        print(f"cannot read {args.file}: {e}", file=sys.stderr)
        return 64

    with open(args.output, "wb") as f:
        f.write(result.data)
    for entry in result.provenance:
        print(f"{entry.code}: {entry.detail}")
    print(
        f"wrote {args.output} ({len(result.data)} bytes; "
        f"{result.records_kept} records kept, {result.records_dropped} dropped)"
    )
    if not result.output_strict_ok:
        print("warning: output does not parse strictly; inspect before uploading", file=sys.stderr)
        return 2
    return 0


def _cmd_analyze(args: argparse.Namespace) -> int:
    from chiptime import metrics  # optional layer: imported only here

    try:
        result = chiptime.parse(args.file, mode=args.mode)
    except chiptime.NotFitError as e:
        print(f"{e.code}: {e.detail}", file=sys.stderr)
        return 4
    except chiptime.FitError as e:
        print(f"{e.code}: {e.detail}", file=sys.stderr)
        return 3
    except OSError as e:
        print(f"cannot read {args.file}: {e}", file=sys.stderr)
        return 64
    settings = metrics.AthleteSettings(
        ftp_w=args.ftp,
        max_hr=args.max_hr,
        resting_hr=args.resting_hr,
        sex=args.sex,
        hr_zone_bounds=_parse_bounds(args.hr_zones, "--hr-zones"),
        power_zone_bounds=_parse_bounds(args.power_zones, "--power-zones"),
    )
    report = metrics.analyze(result, settings)
    if args.json or args.output:
        import json

        payload = json.dumps(
            report.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(payload)
        else:
            print(payload)
    else:
        _print_report(report)
    return _exit_code(result)


def _print_report(report: Any) -> None:
    if not report.sessions:
        print("no activity sessions in this file (nothing to analyze)")
        return
    for i, s in enumerate(report.sessions, 1):
        head = f"session {i}: {s.sport}" + (f"/{s.sub_sport}" if s.sub_sport else "")
        print(head)
        dur = s.duration_s.get("timer") or s.duration_s.get("elapsed")
        bits: list[str] = []
        if dur:
            m, sec = divmod(int(dur + 0.5), 60)
            h, m = divmod(m, 60)
            bits.append(f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}")
        if s.distance_m:
            bits.append(f"{s.distance_m / 1000:.2f} km")
        if s.pace:
            bits.append(f"{s.pace['formatted']} ({s.pace['basis']})")
        elif s.avg_speed_kmh:
            basis = f" ({s.avg_speed_basis})" if s.avg_speed_basis != "timer" else ""
            bits.append(f"{s.avg_speed_kmh:.1f} km/h{basis}")
        if s.avg_primary is not None and s.primary_signal == "power":
            bits.append(f"avg {s.avg_primary:.0f} W")
            if s.weighted_avg_power:
                bits.append(f"weighted {s.weighted_avg_power:.0f} W")
        if s.avg_hr is not None:
            bits.append(f"avg HR {s.avg_hr:.0f}")
        if bits:
            print("  " + " · ".join(bits))
        if s.structure is not None and s.structure.basis != "none":
            labels = "; ".join(g.label for g in s.structure.repeats) or "intervals"
            print(f"  structure [{s.structure.basis}]: {labels}")
        if s.load is not None:
            print(f"  load {s.load.value:.0f} [{s.load.basis}]")
        for ins in s.insights:
            print(f"  {ins.code}: {ins.message}")
        for o in s.omissions:
            print(f"  (omitted) {o}")


def _cmd_parse(args: argparse.Namespace) -> int:
    try:
        result = chiptime.parse(
            args.file,
            mode=args.mode,
            strip_pii=args.strip_pii,
            include_raw=args.include_raw,
            include_unknown=not args.no_unknown,
        )
    except chiptime.NotFitError as e:
        print(f"{e.code}: {e.detail}", file=sys.stderr)
        return 4
    except chiptime.FitError as e:
        print(f"{e.code}: {e.detail}", file=sys.stderr)
        if e.suggestion:
            print(f"suggestion: {e.suggestion}", file=sys.stderr)
        return 3
    except OSError as e:
        print(f"cannot read {args.file}: {e}", file=sys.stderr)
        return 64

    if args.json or args.output:
        payload = result.to_canonical_json()
        if args.output:
            with open(args.output, "wb") as f:
                f.write(payload)
        else:
            sys.stdout.buffer.write(payload + b"\n")
    else:
        _summary(result)
    return _exit_code(result)


def _summary(r: chiptime.ParseResult) -> None:
    print(f"file_type: {r.file_type}   parts: {len(r.parts)}   mode: {r.mode}")
    a = r.activity
    if a is not None:
        if a.device:
            print(f"device: {a.device.manufacturer} product={a.device.product}")
        for i, s in enumerate(a.sessions):
            der = s.derived
            bits = [f"records={s.records.n}"]
            if der.distance_m is not None:
                bits.append(f"distance={der.distance_m:.0f}m")
            if der.elapsed_time_s is not None:
                bits.append(f"elapsed={der.elapsed_time_s:.0f}s")
            if der.timer_time_s is not None:
                bits.append(f"timer={der.timer_time_s:.0f}s")
            if s.rebuilt:
                bits.append("REBUILT")
            if s.discrepancies:
                bits.append(f"discrepancies={len(s.discrepancies)}")
            print(f"session[{i}] {s.sport}: " + "  ".join(bits))
        if a.gaps:
            kinds = ", ".join(f"{g.kind}({g.duration_s:.0f}s)" for g in a.gaps[:6])
            print(f"gaps: {kinds}" + (" …" if len(a.gaps) > 6 else ""))
    if r.recovery:
        rec = r.recovery
        est = f"/{rec.estimated_total_records}(est)" if rec.estimated_total_records else ""
        print(
            f"recovery: {rec.recovered_records}{est} messages,"
            f" {rec.bytes_skipped}B skipped, {rec.resync_count} resync(s)"
        )
    for p in r.provenance:
        print(f"provenance: [{p.code}] {p.detail}")
    for w in r.warnings:
        print(f"warning: [{w.code}] {w.detail}")
    for e in r.errors:
        line = f"error: [{e.code}] {e.detail}"
        if e.suggestion:
            line += f" — {e.suggestion}"
        print(line)


def _cmd_repair(args: argparse.Namespace) -> int:
    from chiptime.repair import NotRepairableError, repair

    try:
        rr = repair(args.file, mode=args.mode)
    except NotRepairableError as e:
        print(f"{e.code}: {e.detail}", file=sys.stderr)
        if e.suggestion:
            print(f"suggestion: {e.suggestion}", file=sys.stderr)
        return 3
    except chiptime.FitError as e:
        print(f"{e.code}: {e.detail}", file=sys.stderr)
        return 3
    except OSError as e:
        print(f"cannot read {args.file}: {e}", file=sys.stderr)
        return 64
    with open(args.output, "wb") as f:
        f.write(rr.data)
    for p in rr.provenance:
        print(f"repair: [{p.code}] {p.detail}")
    if rr.parse_result is not None and rr.parse_result.recovery is not None:
        rec = rr.parse_result.recovery
        print(f"salvage: {rec.recovered_records} messages, {rec.bytes_skipped}B skipped")
    print(f"wrote {args.output} ({len(rr.data)} bytes); strict-valid: {rr.output_strict_ok}")
    return 0 if rr.output_strict_ok else 2


def _cmd_inspect(args: argparse.Namespace) -> int:
    try:
        shown = 0
        for ev in chiptime.iter_frames(args.file):
            if shown >= args.limit:
                print("…")
                break
            if isinstance(ev, FileHeader):
                print(
                    f"{ev.offset:>8}  header    size={ev.size} proto=0x{ev.protocol_version:02X}"
                    f" data_size={ev.data_size} crc_ok={ev.crc_ok}"
                )
            elif isinstance(ev, DefinitionFrame):
                dev = f" +{len(ev.dev_fields)}dev" if ev.dev_fields else ""
                endian = "BE" if ev.big_endian else "LE"
                print(
                    f"{ev.offset:>8}  define    local={ev.local_id} global={ev.global_num}"
                    f" fields={len(ev.fields)}{dev} {endian}"
                )
            elif isinstance(ev, DataFrame):
                comp = f" toff={ev.time_offset}" if ev.time_offset is not None else ""
                print(
                    f"{ev.offset:>8}  data      local={ev.local_id}"
                    f" global={ev.definition.global_num} bytes={len(ev.payload)}{comp}"
                )
            elif isinstance(ev, SkippedBytes):
                print(f"{ev.offset:>8}  SKIPPED   {ev.length} bytes ({ev.reason})")
            elif isinstance(ev, CrcFrame):
                print(f"{ev.offset:>8}  crc       declared=0x{ev.declared:04X} ok={ev.ok}")
            else:
                continue
            shown += 1
        return 0
    except OSError as e:
        print(f"cannot read {args.file}: {e}", file=sys.stderr)
        return 64


def _cmd_validate(args: argparse.Namespace) -> int:
    from chiptime.validate import validate

    try:
        findings = validate(args.file, platform=args.platform)
    except OSError as e:
        print(f"cannot read {args.file}: {e}", file=sys.stderr)
        return 64
    for f in findings:
        print(f"{f.level}: [{f.code}] {f.detail}")
    if any(f.level == "error" for f in findings):
        return 3
    if findings:
        return 2
    print(f"valid for {args.platform}")
    return 0


def _cmd_codes() -> int:
    for title, table in (
        ("errors", ERROR_CODES),
        ("warnings", WARNING_CODES),
        ("provenance", PROVENANCE_CODES),
    ):
        print(f"# {title}")
        for code, desc in table.items():
            print(f"{code}\t{desc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
