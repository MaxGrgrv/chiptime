"""DataFrames → typed Messages: base types, sentinels, scale/offset, enums,
timestamps (incl. compressed), strings, arrays. Field-level salvage per #25.

The wire base type from the definition frame is authoritative for width;
the profile adds naming/semantics only. Sentinels become None BEFORE any
scaling (contract #4). Unknown anything is preserved (contract #6).
"""

from __future__ import annotations

import dataclasses
import re
import struct
from dataclasses import dataclass, field
from typing import ClassVar

from chiptime.errors import Defect, Diagnostic, ProvenanceEntry
from chiptime.frames import DataFrame
from chiptime.message import DevFieldOrigin, FieldValue, Message
from chiptime.profile import BASE_TYPES, ENUMS, MESSAGES, is_invalid, registry
from chiptime.profile.core import FieldDef

FIT_EPOCH_UNIX = 631065600  # 1989-12-31T00:00:00Z (taxonomy #36)
RELATIVE_TS_CEILING = 0x10000000  # below this, date_time is device-relative


def _civil_from_unix(unix: int) -> tuple[int, int, int, int, int, int]:
    """Unix seconds -> (y, m, d, hh, mm, ss) UTC. Hinnant's civil_from_days;
    ~4x faster than fromtimestamp+strftime (F20), equality property-tested."""
    days, rem = divmod(unix, 86400)
    hh, rem = divmod(rem, 3600)
    mm, ss = divmod(rem, 60)
    z = days + 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    return (y + (1 if m <= 2 else 0), m, d, hh, mm, ss)


def fit_ts_to_iso(fit_seconds: int) -> str:
    y, m, d, hh, mm, ss = _civil_from_unix(FIT_EPOCH_UNIX + fit_seconds)
    return f"{y:04d}-{m:02d}-{d:02d}T{hh:02d}:{mm:02d}:{ss:02d}Z"


def fit_ts_to_iso_local(fit_seconds: int) -> str:
    y, m, d, hh, mm, ss = _civil_from_unix(FIT_EPOCH_UNIX + fit_seconds)
    return f"{y:04d}-{m:02d}-{d:02d}T{hh:02d}:{mm:02d}:{ss:02d}"


@dataclass
class DecodeOutput:
    messages: list[Message] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    provenance: list[ProvenanceEntry] = field(default_factory=list)
    defects: list[Defect] = field(default_factory=list)


@dataclass(slots=True)
class _FieldPlan:
    num: int
    base_type_byte: int
    name: str
    fdef: FieldDef | None
    bt: object | None  # BaseType | None (unknown base type)
    struct: struct.Struct | None
    count: int
    size: int
    invalid: int | float | None  # signed-adjusted sentinel, None for floats/n.a.
    is_float: bool
    is_ts253: bool
    fast_number: bool  # scalar, known bt, plain number w/o scale/offset


@dataclass(frozen=True, slots=True)
class _DevDesc:
    name: str | None
    base_type_id: int | None
    scale: float | None
    offset: float | None
    units: str | None


class Decoder:
    """Stateful (timestamp anchor, dev metadata, aggregation) decoder for one FIT stream."""

    def __init__(self) -> None:
        self.last_timestamp: int | None = None
        self.file_id_created: int | None = None
        self._diag_seen: set[tuple[str, str]] = set()
        self._salvage_agg: dict[tuple[int, int, str], list[int]] = {}  # key -> [count, first]
        self._anchor_synthesized = False
        self._anchor_missing_reported = False
        self._hr_ts1024: int | None = None  # hr event_timestamp accumulator (1/1024 s)
        self._csd_total_16ths = 0  # compressed_speed_distance accumulator (#29)
        self._csd_last12: int | None = None
        self._acc_power_wraps = 0  # accumulated_power uint32 wraps (#30)
        self._acc_power_last: int | None = None
        self._plans: dict[int, list[_FieldPlan]] = {}  # id(DefinitionFrame) -> plan
        self._dev_apps: dict[int, tuple[str | None, str | None]] = {}  # idx -> (app_id, vendor)
        self._dev_descs: dict[tuple[int, int], _DevDesc] = {}
        # (message index, placeholder name, dev idx, dev num, raw bytes, big_endian)
        self._unresolved_dev: list[tuple[int, str, int, int, bytes, bool]] = []
        self.out = DecodeOutput()

    # ── public ──────────────────────────────────────────────────────────

    def decode(self, frame: DataFrame) -> Message:
        gnum = frame.definition.global_num
        mdef = MESSAGES.get(gnum)
        name = mdef.name if mdef else f"unknown_{gnum}"
        fields: dict[str, FieldValue] = {}
        pos = 0
        payload = frame.payload
        big = frame.definition.big_endian

        plan = self._plans.get(id(frame.definition))
        if plan is None:
            plan = self._build_plan(frame.definition, mdef, frame.offset)
            self._plans[id(frame.definition)] = plan

        for fp in plan:
            raw_bytes = payload[pos : pos + fp.size]
            pos += fp.size
            fname = fp.name
            bt = fp.bt

            if fp.struct is not None and fp.count == 1:
                raw0 = fp.struct.unpack_from(raw_bytes)[0]
                if fp.fast_number:  # hottest path: plain scalar integer
                    if raw0 == fp.invalid:
                        fields[fname] = FieldValue(None, raw0, fp.fdef.units if fp.fdef else None)
                    else:
                        fdef = fp.fdef
                        v: object
                        if fdef is not None and fdef.scale != 1.0:
                            scaled = raw0 / fdef.scale
                            if fdef.offset:
                                scaled = scaled - fdef.offset
                            v = scaled
                        elif fdef is not None and fdef.offset:
                            v = raw0 - fdef.offset
                        else:
                            v = raw0
                        fields[fname] = FieldValue(v, raw0, fdef.units if fdef else None)
                    continue
                # scalar, but enum/datetime/253/float semantics
                from chiptime.profile.base_types import BaseType

                assert isinstance(bt, BaseType)
                if fp.is_float and raw_bytes == b"\xff" * fp.size:
                    # exact invalid pattern = normal absence, no warning
                    # (muktihari#39: only the all-ones pattern is the sentinel)
                    fields[fname] = FieldValue(None, raw0, fp.fdef.units if fp.fdef else None)
                    continue
                value = self._element(raw0, bt, fp.fdef, name, fname)
                if fp.is_ts253 and isinstance(raw0, int):
                    if not is_invalid(bt, raw0) and raw0 >= RELATIVE_TS_CEILING:
                        self.last_timestamp = raw0
                    if fp.fdef is None:
                        fname = "timestamp"
                        value = self._date_time(raw0, name, fname)
                fields[fname] = FieldValue(value, raw0, fp.fdef.units if fp.fdef else None)
                continue

            if fp.num == 253 and fp.size == 4 and (fp.bt is None or getattr(fp.bt, "size", 0) == 1):
                # fitdecode#33 (Xiaomi pipeline): timestamp declared as byte[4];
                # reassemble per the definition's endianness.
                ts_raw = int.from_bytes(raw_bytes, "big" if big else "little")
                self._diag(
                    "TIMESTAMP_DECLARED_AS_BYTES",
                    f"{name}: field 253 declared as 4 single-byte units;"
                    f" reassembled as uint32 (Xiaomi-pipeline class)",
                    name,
                )
                if ts_raw >= RELATIVE_TS_CEILING:
                    self.last_timestamp = ts_raw
                fields["timestamp"] = FieldValue(
                    self._date_time(ts_raw, name, "timestamp"), ts_raw, "datetime"
                )
                continue
            fields[fname] = self._slow_field(fp, raw_bytes, name, big, frame)

        for dev_spec in frame.definition.dev_fields:
            raw_dev = payload[pos : pos + dev_spec.size]
            pos += dev_spec.size
            idx, num2 = dev_spec.dev_data_index, dev_spec.num
            resolved = self._resolve_dev(idx, num2, raw_dev, fields, big)
            if resolved is None:
                # Missing/null metadata (taxonomy #22a/b, fitparse #62/#124):
                # synthesize a name, keep the data, warn once, allow late back-fill.
                pname = f"dev_{idx}_{num2}"
                app_id, vendor = self._dev_apps.get(idx, (None, None))
                self._diag(
                    "DEV_FIELD_NAME_SYNTHESIZED",
                    f"developer field {idx}/{num2} in {name} has no usable"
                    f" field_description; named {pname}, raw bytes kept",
                    f"dev.{idx}.{num2}",
                )
                fields[pname] = FieldValue(
                    None, raw_dev, None, DevFieldOrigin(idx, num2, app_id, vendor)
                )
                self._unresolved_dev.append(
                    (len(self.out.messages), pname, idx, num2, raw_dev, big)
                )
            else:
                fields[resolved[0]] = resolved[1]

        if gnum == 20:
            self._expand_record_components(fields, frame)
        elif gnum == 21:
            self._resolve_event_subfield(fields)
        elif gnum == 132:
            self._expand_hr(fields, frame)
        if "timestamp_16" in fields:
            self._merge_timestamp16(fields, frame)
        if "left_right_balance" in fields or "left_right_balance_100" in fields:
            self._decode_balance(fields)
        if gnum in (0, 23) and "product" in fields:
            self._resolve_product(fields)

        if frame.time_offset is not None:
            self._compressed_timestamp(frame, fields, name)

        msg = Message(gnum, name, frame.local_id, frame.offset, fields, wire=frame.definition)
        if gnum == 0:  # file_id: remember creation time as anchor of last resort
            created = msg.get_raw("time_created")
            if isinstance(created, int) and created >= RELATIVE_TS_CEILING:
                self.file_id_created = created
        elif gnum == 207:  # developer_data_id (taxonomy #22)
            didx = msg.get("developer_data_index")
            if isinstance(didx, int):
                if didx in self._dev_apps:
                    self._diag(
                        "DEV_INDEX_REDEFINED",
                        f"developer_data_index {didx} redefined by another application"
                        f" mid-file; later definitions apply forward",
                        f"dev.{didx}",
                    )
                app_raw = msg.get_raw("application_id")
                app_hex = app_raw.hex() if isinstance(app_raw, bytes) else None
                manu = msg.get("manufacturer_id")
                self._dev_apps[didx] = (app_hex, manu if isinstance(manu, str) else None)
        elif gnum == 206:  # field_description
            didx = msg.get("developer_data_index")
            fnum = msg.get("field_definition_number")
            if isinstance(didx, int) and isinstance(fnum, int):
                if didx not in self._dev_apps:
                    self._diag(
                        "DEV_DATA_ID_MISSING",
                        f"field_description for developer_data_index {didx} arrived"
                        f" without a developer_data_id message (spec violation; tolerated)",
                        f"dev.{didx}",
                    )
                fname_v = msg.get("field_name")
                bt_v = msg.get("fit_base_type_id")
                sc_v = msg.get("scale")
                of_v = msg.get("offset")
                un_v = msg.get("units")
                self._dev_descs[(didx, fnum)] = _DevDesc(
                    name=fname_v if isinstance(fname_v, str) else None,
                    base_type_id=bt_v if isinstance(bt_v, int) else None,
                    scale=float(sc_v) if isinstance(sc_v, (int, float)) else None,
                    offset=float(of_v) if isinstance(of_v, (int, float)) else None,
                    units=un_v if isinstance(un_v, str) else None,
                )
        self.out.messages.append(msg)
        return msg

    def finish(self) -> DecodeOutput:
        resolved_late = 0
        for mi, pname, idx, num, raw_dev, big in self._unresolved_dev:
            msg = self.out.messages[mi]
            existing = {k: v for k, v in msg.fields.items() if k != pname}
            resolved = self._resolve_dev(idx, num, raw_dev, existing, big)
            if resolved is None:
                continue
            existing[resolved[0]] = resolved[1]
            self.out.messages[mi] = dataclasses.replace(msg, fields=existing)
            resolved_late += 1
        if resolved_late:
            self.out.provenance.append(
                ProvenanceEntry(
                    "DEV_FIELD_RESOLVED_LATE",
                    "reinterpreted",
                    "stream",
                    f"{resolved_late} developer field value(s) re-resolved after their"
                    f" field_description arrived later in the file",
                    data={"count": resolved_late},
                )
            )
        for (def_offset, fnum, why), (n, first) in sorted(self._salvage_agg.items()):
            self.out.provenance.append(
                ProvenanceEntry(
                    "FIELD_RAW_SALVAGED",
                    "reinterpreted",
                    f"definition@{def_offset}.field_{fnum}",
                    f"{why}; raw bytes kept for {n} message(s)",
                    byte_offset=first,
                    data={"count": n, "definition_offset": def_offset, "field_num": fnum},
                )
            )
        return self.out

    # ── internals ───────────────────────────────────────────────────────

    def _element(
        self, raw: int | float, bt: object, fdef: FieldDef | None, mname: str, fname: str
    ) -> object | None:
        from chiptime.profile.base_types import BaseType

        assert isinstance(bt, BaseType)
        if bt.name in ("float32", "float64"):
            if raw != raw or raw in (float("inf"), float("-inf")):
                # Sentinel pattern is itself a NaN; either way the value is absent (#35).
                self._diag(
                    "NONFINITE_FLOAT_NULLED",
                    f"non-finite float in {mname}.{fname}; treated as absent",
                    f"{mname}.{fname}",
                )
                return None
        elif is_invalid(bt, raw):  # sentinel → absent (taxonomy #26), BEFORE scaling
            return None

        if fdef is None:
            return raw

        if fdef.kind.startswith("enum:"):
            mapping = ENUMS.get(fdef.kind.removeprefix("enum:"), {})
            return mapping.get(int(raw), raw)  # unknown enum → raw int (taxonomy #24)
        if fdef.kind == "date_time":
            return self._date_time(int(raw), mname, fname)
        if fdef.kind == "local_date_time":
            if int(raw) < RELATIVE_TS_CEILING:
                self._diag(
                    "RELATIVE_TIMESTAMP",
                    f"{mname}.{fname} is below 0x10000000 (device-relative); value kept raw",
                    f"{mname}.{fname}",
                )
                return None
            return fit_ts_to_iso_local(int(raw))

        value: int | float = raw
        if fdef.scale != 1.0:
            value = value / fdef.scale
        if fdef.offset:
            value = value - fdef.offset
        return value

    def _date_time(self, raw: int, mname: str, fname: str) -> str | None:
        if raw < RELATIVE_TS_CEILING:
            self._diag(
                "RELATIVE_TIMESTAMP",
                f"{mname}.{fname} is below 0x10000000 (device-relative); value kept raw",
                f"{mname}.{fname}",
            )
            return None
        return fit_ts_to_iso(raw)

    def _string(self, raw: bytes, mname: str, fname: str) -> FieldValue:
        """Strings: up-to-NUL-or-end, tolerant decode. Multiple properly
        terminated segments = a string array (muktihari#623); an unterminated
        tail after terminated segments is padding junk, never decoded
        (muktihari#436)."""
        segments: list[str] = []
        pos = 0
        replaced = False
        while pos < len(raw):
            nul = raw.find(b"\x00", pos)
            if nul < 0:
                if not segments:  # single unterminated string (fitparse#75)
                    self._diag(
                        "STRING_UNTERMINATED",
                        f"{mname}.{fname} has no NUL terminator; whole buffer used",
                        f"{mname}.{fname}",
                    )
                    text = raw[pos:].decode("utf-8", errors="replace")
                    replaced = replaced or "�" in text
                    segments.append(text)
                break  # terminated segments exist: tail is padding junk
            if nul == pos:
                break  # empty segment = end of array
            text = raw[pos:nul].decode("utf-8", errors="replace")
            if "�" in text and segments:
                break  # undecodable after valid segments = padding junk (#436)
            replaced = replaced or "�" in text
            segments.append(text)
            pos = nul + 1
        if replaced:
            self._diag(
                "STRING_DECODE_REPLACED",
                f"{mname}.{fname} contained invalid UTF-8; replacement characters used",
                f"{mname}.{fname}",
            )
        segments = [t for t in segments if t]
        if not segments:
            return FieldValue(None, raw)
        if len(segments) == 1:
            return FieldValue(segments[0], raw)
        return FieldValue(segments, raw)

    def _compressed_timestamp(
        self, frame: DataFrame, fields: dict[str, FieldValue], mname: str
    ) -> None:
        toff = frame.time_offset
        assert toff is not None
        if "timestamp" in fields:
            self._diag(
                "COMPRESSED_AND_EXPLICIT_TIMESTAMP",
                f"{mname} carries both a compressed header and field 253; explicit value kept",
                mname,
            )
            return
        anchor = self.last_timestamp
        if anchor is None and self.file_id_created is not None:
            # Taxonomy #21 prescription: anchor from file_id creation time, with provenance.
            anchor = self.file_id_created
            if not self._anchor_synthesized:
                self._anchor_synthesized = True
                self.out.provenance.append(
                    ProvenanceEntry(
                        "TIMESTAMP_ANCHOR_FROM_FILE_ID",
                        "synthesized",
                        "stream",
                        "compressed timestamps appeared before any full timestamp;"
                        " anchored from file_id.time_created",
                        byte_offset=frame.offset,
                    )
                )
        if anchor is None:
            if not self._anchor_missing_reported:
                self._anchor_missing_reported = True
                self.out.defects.append(
                    Defect(
                        "FIT_MISSING_TIMESTAMP_ANCHOR",
                        "compressed-timestamp record appeared before any full timestamp"
                        " and file_id has no usable time_created",
                        frame.offset,
                        "data",
                    )
                )
            return
        ts = (anchor & ~0x1F) + toff + (0x20 if toff < (anchor & 0x1F) else 0)
        self.last_timestamp = ts
        fields["timestamp"] = FieldValue(fit_ts_to_iso(ts), ts, "datetime")

    def _build_plan(self, definition: object, mdef: object, first_offset: int) -> list[_FieldPlan]:
        from chiptime.frames import DefinitionFrame
        from chiptime.profile.base_types import _SIGNED_INVALID
        from chiptime.profile.core import MessageDef

        assert isinstance(definition, DefinitionFrame)
        endian = ">" if definition.big_endian else "<"
        plan: list[_FieldPlan] = []
        for spec in definition.fields:
            fdef = mdef.fields.get(spec.num) if isinstance(mdef, MessageDef) else None
            fname = fdef.name if fdef else f"field_{spec.num}"
            bt = BASE_TYPES.get(spec.base_type)
            st = None
            count = 0
            invalid: int | float | None = None
            is_float = False
            fast = False
            if bt is not None and bt.struct_code is not None:
                count = spec.size // bt.size
                if count >= 1:
                    st = struct.Struct(f"{endian}{count}{bt.struct_code}")
                is_float = bt.name in ("float32", "float64")
                if not is_float:
                    invalid = _SIGNED_INVALID.get(bt.name, bt.invalid)
                fast = (
                    count == 1
                    and spec.size == bt.size
                    and spec.num != 253
                    and not is_float  # floats need _element's non-finite diagnostics
                    and (fdef is None or fdef.kind == "number")
                )
            plan.append(
                _FieldPlan(
                    num=spec.num,
                    base_type_byte=spec.base_type,
                    name=fname,
                    fdef=fdef,
                    bt=bt,
                    struct=st,
                    count=count,
                    size=spec.size,
                    invalid=invalid,
                    is_float=is_float,
                    is_ts253=(spec.num == 253 and bt is not None and bt.name == "uint32"),
                    fast_number=fast,
                )
            )
        return plan

    def _slow_field(
        self, fp: _FieldPlan, raw_bytes: bytes, mname: str, big: bool, frame: DataFrame
    ) -> FieldValue:
        """Everything the fast paths don't cover: unknown base types, strings,
        byte fields, arrays, size mismatches — semantics identical to pre-plan."""
        from chiptime.profile.base_types import BaseType

        spec_num = fp.num
        bt = fp.bt
        if bt is None:  # unknown base type (taxonomy #25)
            self._salvage(
                frame.definition.offset,
                spec_num,
                "unknown base type",
                frame.offset,
                defect_code="FIT_BASE_TYPE_INVALID",
                defect_detail=f"field {spec_num} declares unknown base type"
                f" 0x{fp.base_type_byte:02X}",
            )
            return FieldValue(None, raw_bytes)
        assert isinstance(bt, BaseType)
        if bt.name == "string":
            return self._string(raw_bytes, mname, fp.name)
        if bt.name == "byte":
            bval = None if all(b == 0xFF for b in raw_bytes) else raw_bytes
            return FieldValue(bval, raw_bytes)
        if fp.count == 0:
            self._salvage(
                frame.definition.offset,
                spec_num,
                f"size {fp.size} smaller than base type {bt.name}",
                frame.offset,
            )
            return FieldValue(None, raw_bytes)
        if fp.size % bt.size:
            self._salvage(
                frame.definition.offset,
                spec_num,
                f"size {fp.size} not a multiple of {bt.name} ({bt.size}); trailing bytes kept raw",
                frame.offset,
                defect_code="FIT_FIELD_SIZE_INVALID",
                defect_detail=f"field {spec_num} size {fp.size} not a multiple"
                f" of {bt.name} size {bt.size}",
            )
        assert fp.struct is not None
        raws = fp.struct.unpack_from(raw_bytes)
        if fp.is_float:
            values = [
                None
                if raw_bytes[i * bt.size : (i + 1) * bt.size] == b"\xff" * bt.size
                else self._element(r, bt, fp.fdef, mname, fp.name)
                for i, r in enumerate(raws)
            ]
        else:
            values = [self._element(r, bt, fp.fdef, mname, fp.name) for r in raws]
        raw_out: object = list(raws) if fp.count > 1 else raws[0]
        if fp.count > 1:
            while values and values[-1] is None:  # sentinel tails (taxonomy #34)
                values.pop()
            value: object = values if values else None
        else:
            value = values[0]
        return FieldValue(value, raw_out, fp.fdef.units if fp.fdef else None)

    def _resolve_dev(
        self, idx: int, num: int, raw: bytes, existing: dict[str, FieldValue], big: bool
    ) -> tuple[str, FieldValue] | None:
        """Decode a developer field per its field_description; None → caller synthesizes."""
        desc = self._dev_descs.get((idx, num))
        if desc is None or not desc.name:
            return None
        base = _sanitize_field_name(desc.name)
        if not base:
            return None
        app_id, vendor = self._dev_apps.get(idx, (None, None))
        bt = BASE_TYPES.get(desc.base_type_id) if desc.base_type_id is not None else None
        value: object
        wire: object
        if bt is None:
            value, wire = (raw if any(b != 0xFF for b in raw) else None), raw
        elif bt.name == "string":
            nul = raw.find(b"\x00")
            text = (raw if nul < 0 else raw[:nul]).decode("utf-8", errors="replace")
            value, wire = (text or None), raw
        elif bt.struct_code is None:  # byte
            value, wire = (raw if any(b != 0xFF for b in raw) else None), raw
        elif len(raw) % bt.size or len(raw) == 0:
            value, wire = None, raw
        else:
            count = len(raw) // bt.size
            endian = ">" if big else "<"
            raws = struct.unpack(f"{endian}{count}{bt.struct_code}", raw)
            vals: list[object] = []
            for r in raws:
                nonfinite = isinstance(r, float) and (r != r or r in (float("inf"), float("-inf")))
                if nonfinite or is_invalid(bt, r):
                    vals.append(None)
                else:
                    v: int | float = r
                    if desc.scale not in (None, 0.0, 1.0):
                        assert desc.scale is not None
                        v = v / desc.scale
                    if desc.offset:
                        v = v - desc.offset
                    vals.append(v)
            if count == 1:
                value, wire = vals[0], raws[0]
            else:
                while vals and vals[-1] is None:
                    vals.pop()
                value, wire = (vals if vals else None), list(raws)
        match = registry.lookup(vendor, desc.name)
        units = desc.units or (match.units if match else None)
        fname = base if base not in existing else f"{base}_{idx}_{num}"
        origin = DevFieldOrigin(idx, num, app_id, vendor, match.canonical_name if match else None)
        return fname, FieldValue(value, wire, units, origin)

    def _expand_record_components(self, fields: dict[str, FieldValue], frame: DataFrame) -> None:
        """compressed_speed_distance (#29): 12-bit speed (1/100 m/s) + 12-bit
        rolling distance (1/16 m, wraps every 256 m). Accumulated_power (#30):
        unwrap uint32 wraps."""
        csd = fields.get("compressed_speed_distance")
        if csd is not None and isinstance(csd.raw, bytes) and len(csd.raw) == 3:
            b0, b1, b2 = csd.raw
            speed_raw = b0 | ((b1 & 0x0F) << 8)
            dist12 = (b1 >> 4) | (b2 << 4)
            if speed_raw != 0xFFF or dist12 != 0xFFF:
                if self._csd_last12 is None:
                    self._csd_last12 = dist12
                delta = (dist12 - self._csd_last12) % 4096
                self._csd_total_16ths += delta
                self._csd_last12 = dist12
                if "speed" not in fields and speed_raw != 0xFFF:
                    fields["speed"] = FieldValue(speed_raw / 100.0, speed_raw, "m/s")
                if "distance" not in fields:
                    fields["distance"] = FieldValue(
                        self._csd_total_16ths / 16.0, self._csd_total_16ths, "m"
                    )
                self._salvage(
                    frame.definition.offset,
                    8,
                    "compressed_speed_distance expanded",
                    frame.offset,
                )
        acc = fields.get("accumulated_power")
        if acc is not None and isinstance(acc.raw, int):
            if self._acc_power_last is not None and acc.raw < self._acc_power_last:
                self._acc_power_wraps += 1
                self._salvage(
                    frame.definition.offset,
                    29,
                    "accumulated_power wrapped its uint32; unwrapped",
                    frame.offset,
                )
            self._acc_power_last = acc.raw
            if self._acc_power_wraps:
                fields["accumulated_power"] = FieldValue(
                    acc.raw + self._acc_power_wraps * 2**32, acc.raw, "watts"
                )

    def _merge_timestamp16(self, fields: dict[str, FieldValue], frame: DataFrame) -> None:
        """timestamp_16 = low 16 bits of the rolling full timestamp
        (fitdecode#28, fitparse#46): full = last + ((t16 - (last & 0xFFFF)) & 0xFFFF)."""
        t16 = fields["timestamp_16"].raw
        if not isinstance(t16, int) or t16 == 0xFFFF or self.last_timestamp is None:
            return
        full = self.last_timestamp + ((t16 - (self.last_timestamp & 0xFFFF)) & 0xFFFF)
        self.last_timestamp = full
        if "timestamp" not in fields:
            fields["timestamp"] = FieldValue(fit_ts_to_iso(full), full, "datetime")
            self._salvage(
                frame.definition.offset,
                254,
                "timestamp_16 merged onto rolling timestamp",
                frame.offset,
            )

    def _expand_hr(self, fields: dict[str, FieldValue], frame: DataFrame) -> None:
        """hr.event_timestamp_12 → 12-bit LSB-stream deltas with 0xFFF rollover
        against the accumulated event_timestamp anchor (fitparse#69/#122 — the
        expansion fitparse still gets wrong; algorithm per muktihari#474)."""
        anchor_fv = fields.get("event_timestamp")
        if anchor_fv is not None:
            raws = anchor_fv.raw if isinstance(anchor_fv.raw, list) else [anchor_fv.raw]
            for r in reversed(raws):
                if isinstance(r, int) and r != 0xFFFFFFFF:
                    self._hr_ts1024 = r
                    break
        packed = fields.get("event_timestamp_12")
        if packed is None or not isinstance(packed.raw, bytes):
            return
        if self._hr_ts1024 is None:
            self._diag(
                "HR_EXPANSION_NO_ANCHOR",
                "hr.event_timestamp_12 present before any full event_timestamp;"
                " samples not expandable",
                "hr",
            )
            return
        total = int.from_bytes(packed.raw, "little")
        n = (len(packed.raw) * 8) // 12
        anchor = self._hr_ts1024
        out_raw: list[int] = []
        for i in range(n):
            v = (total >> (12 * i)) & 0xFFF
            if v == 0xFFF:
                continue
            anchor = (anchor & ~0xFFF) + v + (0x1000 if v < (anchor & 0xFFF) else 0)
            out_raw.append(anchor)
        self._hr_ts1024 = anchor
        if out_raw:
            fields["event_timestamp_expanded"] = FieldValue(
                [r / 1024.0 for r in out_raw], out_raw, "s"
            )
            self._salvage(
                frame.definition.offset,
                10,
                f"event_timestamp_12 expanded into {len(out_raw)} sample timestamp(s)",
                frame.offset,
            )

    def _decode_balance(self, fields: dict[str, FieldValue]) -> None:
        """left_right_balance bit decode (#65; fitdecode#38, fit-swift-sdk#13):
        flag bit marks the RIGHT side; low bits are that side's percent."""
        for fname, flag_bit, mask, scale in (
            ("left_right_balance", 0x80, 0x7F, 1.0),
            ("left_right_balance_100", 0x8000, 0x3FFF, 100.0),
        ):
            fv = fields.get(fname)
            if fv is None or not isinstance(fv.raw, int):
                continue
            val = fv.raw & mask
            pct = val / scale
            if pct > 100.0:
                continue  # not plausibly a percentage; leave raw untouched
            right = bool(fv.raw & flag_bit)
            fields["right_balance_pct"] = FieldValue(
                pct if right else 100.0 - pct, fv.raw, "percent"
            )

    def _resolve_product(self, fields: dict[str, FieldValue]) -> None:
        """product subfield naming (fitparse PR#131): resolve through
        manufacturer-specific enums per the profile's reference values."""
        manu = fields.get("manufacturer")
        prod = fields.get("product")
        if manu is None or prod is None or not isinstance(prod.value, int):
            return
        enum_name = None
        if manu.value in ("garmin", "dynastream", "dynastream_oem", "tacx"):
            enum_name = "garmin_product"
        elif manu.value == "favero_electronics":
            enum_name = "favero_product"
        if enum_name is None:
            return
        mapped = ENUMS.get(enum_name, {}).get(prod.value)
        if mapped is not None:
            fields["product"] = FieldValue(mapped, prod.raw, prod.units, prod.developer)

    _TIMER_TRIGGER: ClassVar[dict[int, str]] = {
        0: "manual",
        1: "auto",
        2: "fitness_equipment",
    }

    def _resolve_event_subfield(self, fields: dict[str, FieldValue]) -> None:
        """event.data dynamic resolution (#31): meaning switches on event type."""
        ev = fields.get("event")
        data = fields.get("data")
        if ev is None or data is None or not isinstance(data.raw, int):
            return
        if ev.value == "timer" and "timer_trigger" not in fields:
            fields["timer_trigger"] = FieldValue(
                self._TIMER_TRIGGER.get(data.raw, data.raw), data.raw
            )

    def _salvage(
        self,
        def_offset: int,
        field_num: int,
        why: str,
        first_offset: int,
        *,
        defect_code: str | None = None,
        defect_detail: str | None = None,
    ) -> None:
        key = (def_offset, field_num, why)
        entry = self._salvage_agg.get(key)
        if entry is None:
            self._salvage_agg[key] = [1, first_offset]
            if defect_code is not None:  # surfaced once; strict mode raises on it
                self.out.defects.append(
                    Defect(defect_code, defect_detail or why, first_offset, "data")
                )
        else:
            entry[0] += 1

    def _diag(self, code: str, detail: str, scope: str) -> None:
        if (code, scope) in self._diag_seen:
            return
        self._diag_seen.add((code, scope))
        self.out.diagnostics.append(Diagnostic(code, detail, scope))


_NAME_RE = re.compile(r"[^a-z0-9]+")


def _sanitize_field_name(name: str) -> str:
    return _NAME_RE.sub("_", name.strip().lower()).strip("_")
