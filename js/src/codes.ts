/**
 * GENERATED FILE -- do not edit. Regenerate with:
 *
 *     uv run --project python python scripts/gen_codes_ts.py
 *
 * The machine-readable code registries, transcoded from `python/src/chiptime/errors.py`
 * so the two languages cannot disagree about a contract consumers branch on
 * (contract #5; `docs/for-agents.md` is generated from the same tables).
 *
 * The error classes themselves live in `errors.ts`, hand-written. This module emits
 * the defect-to-class mapping as a string kind rather than a class reference, so it
 * imports nothing and there is no cycle.
 */

/** Which `FitError` subclass a defect code maps to. Resolved in `errors.ts`. */
export type ErrorKind =
  | "NotFitError"
  | "EmptyFileError"
  | "HeaderError"
  | "TruncatedError"
  | "CrcMismatchError"
  | "ProtocolError";

/** Fatal and collected error codes (contract #5). */
export const ERROR_CODES: Readonly<Record<string, string>> = {
  "DISTANCE_NOT_MEASURED": "The file records no distance to rescale.",
  "DISTANCE_SCALE_OUT_OF_RANGE": "Rescaling distance by the requested factor would overflow a field's wire type; nothing was written.",
  "FIT_BASE_TYPE_INVALID": "A definition declares an unknown base type.",
  "FIT_CRC_MISMATCH": "The file CRC does not match the content.",
  "FIT_CRC_MISSING": "The 2-byte file CRC trailer is absent.",
  "FIT_DATA_SIZE_MISMATCH": "The header's data_size disagrees with the actual bytes.",
  "FIT_DEFINITION_INVALID": "A definition message is malformed.",
  "FIT_EMPTY": "The file contains no bytes.",
  "FIT_FIELD_SIZE_INVALID": "A field's size is not a multiple of its base type size.",
  "FIT_HEADER_CRC_MISMATCH": "The 14-byte header's CRC is nonzero and wrong.",
  "FIT_HEADER_INVALID": "The file header is malformed (size, magic, or fields).",
  "FIT_MISSING_TIMESTAMP_ANCHOR": "A compressed-timestamp record has no timestamp anchor.",
  "FIT_NO_CONTENT": "Structurally valid container, zero messages; data genuinely absent (#16).",
  "FIT_TOO_SMALL": "The file is smaller than any valid FIT header.",
  "FIT_TRAILING_JUNK": "Bytes after the final CRC are not a chained FIT file.",
  "FIT_TRUNCATED": "The file ends before its declared content is complete.",
  "FIT_UNDEFINED_LOCAL_TYPE": "A data message references a local type with no definition.",
  "NOT_FIT_FORMAT": "The content is not FIT (detail names what it looks like).",
  "REPAIR_NOTHING_TO_SALVAGE": "Nothing usable survives parsing; repair refuses to fabricate data (#16).",
  "SCRUB_NOTHING_SELECTED": "scrub() was called with every category disabled and no location option; nothing was written.",
  "TIME_SHIFT_OUT_OF_RANGE": "A requested time shift would push a timestamp outside the representable FIT range (or onto the invalid sentinel); no bytes were written.",
  "TRIM_BAD_BOUND": "A trim bound could not be interpreted as a time; use an ISO timestamp or a relative offset like '+5m' / '-10m'.",
  "TRIM_EMPTY_RESULT": "The requested trim window keeps no data; nothing was written.",
  "TRIM_NO_RECORDS": "The file has no record messages, so trimmed totals could not be recomputed; nothing was written.",
  "TRIM_NO_WINDOW": "trim() was called without a window; pass after= and/or before=.",
};
/** Non-fatal observations surfaced in `warnings[]`. */
export const WARNING_CODES: Readonly<Record<string, string>> = {
  "ACTIVITY_MESSAGE_MISSING": "No activity message present (#96); repair can synthesize.",
  "COMPRESSED_AND_EXPLICIT_TIMESTAMP": "Record had both timestamp forms; explicit kept.",
  "DEV_DATA_ID_MISSING": "field_description references a developer_data_index that was never announced.",
  "DEV_FIELD_NAME_SYNTHESIZED": "Developer field lacked usable metadata; name synthesized, data kept.",
  "DEV_INDEX_REDEFINED": "A developer_data_index was redefined mid-file by another app.",
  "DISTANCE_DECREASES": "Distance stream decreases (#59).",
  "DISTANCE_FROZEN": "Distance frozen while moving; dead distance source (#59).",
  "DISTANCE_RESCALED_PAIR": "Distance was rescaled; speed was scaled by the same factor so the stream stays internally consistent.",
  "DISTANCE_RESET": "Distance resets to zero mid-activity (#59).",
  "ENHANCED_PAIR_DISAGREES": "speed/altitude and their enhanced_ twins disagree; enhanced kept.",
  "FIT_CRC_MISMATCH": "File CRC is wrong but content decodes; continued.",
  "FIT_CRC_MISSING": "File CRC trailer absent; content used as-is.",
  "FIT_DATA_SIZE_MISMATCH": "Header data_size is wrong; trusting actual content.",
  "FIT_HEADER_CRC_MISMATCH": "Header CRC is wrong; continued.",
  "FIT_HEADER_INVALID": "Header is nonstandard; continued on best interpretation.",
  "FIT_MISSING_TIMESTAMP_ANCHOR": "Compressed timestamps had no anchor; those stamps absent.",
  "FIT_TRAILING_JUNK": "Bytes after the final CRC are not a chained FIT file; ignored.",
  "HR_EXPANSION_NO_ANCHOR": "hr.event_timestamp_12 appeared before any full event_timestamp; samples not expandable.",
  "HR_FLATLINE": "Heart rate flatlined for 2+ minutes; sensor suspect (#62).",
  "HR_IMPLAUSIBLE": "Heart-rate samples above the physiological ceiling; flagged (#62).",
  "LAP_COVERAGE_GAP": "Laps do not cover the session span (#94).",
  "LAP_ZERO_DURATION": "Zero-duration laps; double button press (#94).",
  "LOCAL_TIMESTAMP_IMPLAUSIBLE": "activity.local_timestamp is impossible for any real timezone (Zwift 1989 bug class).",
  "MOVEMENT_WITHOUT_DISTANCE": "Speed present but distance never advances (#97).",
  "NONFINITE_FLOAT_NULLED": "A float field carried NaN/Infinity; treated as absent.",
  "NUM_SESSIONS_MISMATCH": "activity.num_sessions disagrees with actual session count.",
  "POOL_LENGTH_IMPLAUSIBLE": "Distance/lengths imply an implausible pool size (#73).",
  "POOL_ZERO_LENGTH": "Active pool lengths under 2 s; push-off artifacts (#73).",
  "POWER_IMPLAUSIBLE": "Power above 2500 W; flagged, never removed (#63).",
  "RECORDS_OUTSIDE_SESSIONS": "Records fall outside every session's bounds; attached to nearest.",
  "RELATIVE_TIMESTAMP": "A date_time value is device-relative (< 0x10000000), not absolute.",
  "SCRUB_ALL_POSITIONS_CONCEALED": "Every GPS point fell inside the concealment radius, so the scrubbed file has no route left at all.",
  "SPORT_PAIR_IMPLAUSIBLE": "Sport was edited while a non-generic sub-sport was left in place; verify the pair is what you intended (chiptime never guesses a replacement).",
  "STRING_DECODE_REPLACED": "A string field contained invalid UTF-8; replacements used.",
  "STRING_UNTERMINATED": "A string field had no NUL terminator; whole buffer used.",
  "SUMMARY_AVG_EXCEEDS_MAX": "A declared average exceeds its declared maximum (#93).",
  "SUMMARY_NEGATIVE_TOTAL": "A declared total is negative (#93).",
  "TIMER_STOP_WITHOUT_START": "Timer stop event had no preceding start; interval opened at first record.",
  "TIMESTAMPS_AFTER_CREATION": "Records postdate file_id.time_created by more than 7 days; device clock suspect.",
  "TIMESTAMP_DECLARED_AS_BYTES": "Field 253 declared as byte[4]; reassembled (Xiaomi-pipeline class).",
  "UNRELIABLE_ABSOLUTE_TIME": "Timestamps predate 2010; device likely never got GPS time. Relative timeline kept.",
  "ZERO_DURATION_SESSION": "Session declares zero duration but contains records (#97).",
};
/** Every drop, repair, synthesis and reinterpretation (contract #1). */
export const PROVENANCE_CODES: Readonly<Record<string, string>> = {
  "DEVICE_EDITED": "Declared recording-device identity rewritten at the user's explicit request.",
  "DEV_FIELD_RESOLVED_LATE": "Developer fields re-resolved after their field_description arrived later in the file.",
  "DISTANCE_RESCALED": "Recorded distance (and speed) scaled to a user-supplied total, with summaries updated so records and totals still agree.",
  "ENHANCED_PAIR_MERGED": "enhanced_speed/altitude merged into the base stream (enhanced preferred, taxonomy #28).",
  "FIELD_RAW_SALVAGED": "Field bytes undecodable as declared type; raw bytes kept.",
  "GPS_SPIKES_DROPPED": "Physically impossible GPS bounce spikes removed (lenient) or flagged (forensic) (#53).",
  "NULL_ISLAND_DROPPED": "Records at exactly (0,0) nulled or flagged (#51).",
  "PARTIAL_RECORD_DISCARDED": "Trailing bytes formed an incomplete record; discarded.",
  "PII_BODY_METRICS_REMOVED": "Configured physiology (threshold power, max/resting heart rate, VO2max) removed at the user's request; workout measurements are untouched.",
  "PII_IDENTITY_REMOVED": "Identity data (profile, name, age, gender, body size) removed at the user's request.",
  "PII_LOCATION_CONCEALED": "GPS coordinates near the route endpoints were nulled at the user's request; they decode as absent, never as zero.",
  "PII_SERIALS_REMOVED": "Device serial numbers and ANT device ids removed at the user's request.",
  "PII_STRIPPED": "Personally identifying content removed (strip_pii=True).",
  "PREAMBLE_GARBAGE_SKIPPED": "Garbage before the FIT header skipped; header re-anchored.",
  "RECORDS_REORDERED": "Records were not in chronological order; stably sorted (ADR-0005 \u00a71).",
  "REPAIR_ACTIVITY_SYNTHESIZED": "Repair synthesized the activity message (#96).",
  "REPAIR_EVENTS_SYNTHESIZED": "Repair synthesized timer start/stop events (#96).",
  "REPAIR_FILE_ID_SYNTHESIZED": "Repair synthesized a missing file_id message.",
  "REPAIR_LAP_SYNTHESIZED": "Repair synthesized one covering lap.",
  "REPAIR_LOCAL_TIMESTAMP_DROPPED": "Implausible local_timestamp not re-emitted (Zwift bug class, #37).",
  "REPAIR_REENCODED": "Repair re-encoded the file canonically; CRCs recomputed.",
  "REPAIR_SESSION_SYNTHESIZED": "Repair synthesized the session message from records (#95).",
  "RESYNC_SKIPPED_BYTES": "Undecodable bytes skipped; decoding resumed at the next plausible definition frame.",
  "SESSION_REBUILT": "No session message; session synthesized from records (#95).",
  "SPORT_EDITED": "Declared sport/sub-sport rewritten at the user's explicit request.",
  "STREAM_STOPPED_AT_DEFECT": "Decoding stopped at a structural defect; prefix salvaged.",
  "TIMER_STOP_SYNTHESIZED": "No final timer stop; timer closed at the last record.",
  "TIMESTAMPS_SHIFTED": "Every profile-typed timestamp shifted by a user-supplied offset.",
  "TIMESTAMP_ANCHOR_FROM_FILE_ID": "Compressed timestamps anchored from file_id.time_created.",
  "TRIM_LAP_DROPPED": "A lap not wholly inside the trim window was removed; its in-window records were kept.",
  "TRIM_RECORDS_DROPPED": "Records (and pool lengths) outside the requested trim window were removed at the user's explicit request.",
  "TRIM_SUMMARIES_REBUILT": "Session and activity totals were recomputed from the records that survived a trim, so the file cannot carry stale summaries.",
  "TRUNCATED_TAIL_SALVAGED": "File ends mid-content; complete records before the cut kept.",
  "UNKNOWN_MESSAGES_OMITTED": "Unknown-message content omitted (include_unknown=False).",
  "VIRTUAL_GPS_EXEMPT": "Virtual-world coordinates exempt from plausibility gating (#57).",
  "ZIP_ENTRIES_CHAINED": "Multiple .fit entries in a zip parsed as chained parts.",
};
/** Defect code to the `FitError` subclass it raises as in strict mode. */
export const DEFECT_ERROR_KIND: Readonly<Record<string, ErrorKind>> = {
  "FIT_BASE_TYPE_INVALID": "ProtocolError",
  "FIT_CRC_MISMATCH": "CrcMismatchError",
  "FIT_CRC_MISSING": "TruncatedError",
  "FIT_DATA_SIZE_MISMATCH": "HeaderError",
  "FIT_DEFINITION_INVALID": "ProtocolError",
  "FIT_EMPTY": "EmptyFileError",
  "FIT_FIELD_SIZE_INVALID": "ProtocolError",
  "FIT_HEADER_CRC_MISMATCH": "CrcMismatchError",
  "FIT_HEADER_INVALID": "HeaderError",
  "FIT_MISSING_TIMESTAMP_ANCHOR": "ProtocolError",
  "FIT_TOO_SMALL": "NotFitError",
  "FIT_TRAILING_JUNK": "ProtocolError",
  "FIT_TRUNCATED": "TruncatedError",
  "FIT_UNDEFINED_LOCAL_TYPE": "ProtocolError",
  "NOT_FIT_FORMAT": "NotFitError",
};
