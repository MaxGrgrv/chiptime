# FIT Parsing Edge-Case Taxonomy
### Test corpus checklist for a recovery-grade FIT parser
*Compiled from: Garmin FIT SDK + Cookbook, GOTOES, FitFileLab, FIT File Viewer, Fit File Repair Tool (FFRT) manual, python-fitparse / fitdecode issue trackers, Garmin & Zwift forums, Strava support docs.*

Legend for each item: what breaks → what a recovery-grade parser should do.
Every item is a target file for the golden-file corpus. Items marked ★ are ones you can generate from your own devices/archive.

---

## A. File-level & structural corruption

1. **Zero-byte / near-empty file** — device crashed before writing header. → Detect instantly, error `FIT_EMPTY`, no partial output.
2. **Truncated mid-record** — battery death, watch crash, interrupted USB/sync transfer. The most common corruption class. → Salvage all complete records, report `recovered_records / estimated_total`, rebuild session summary from records. ★
3. **Truncated mid-definition-message** — worse variant; the cut lands inside a definition. → Stop at last valid frame boundary, salvage prior data.
4. **Missing or invalid file CRC** (2-byte trailer). Some devices ship files with wrong CRCs even when data is fine — fitparse added `--ignore-crc` specifically because "some devices can write invalid CRCs." → CRC mismatch = warning + continue by default; strict mode available; always recompute CRC on output.
5. **Header CRC invalid** — note the spec allows header CRC of `0x0000` (legal!). Distinguish "zero = skip check" from "nonzero = must match."
6. **Invalid header size** — not 12 or 14 bytes (fitparse issue #1: "Bad .FIT file header: Invalid header size"). Some ancient devices/apps write nonstandard headers. → Attempt both known sizes; scan for `.FIT` magic.
7. **`data_size` in header ≠ actual bytes present** — file grew or shrank relative to declared size. → Trust actual content, warn, parse to real end.
8. **Missing `.FIT` magic string** in header while rest is valid.
9. **Garbage bytes *before* first valid record** — seen on Edge 1050: corrupt data before the first data record, with GPS/timestamps "clearly out of whack." → Resync scan: find first valid definition frame, skip preamble, log dropped byte count. ★ (Edge-series firmware bugs)
10. **Garbage/unreadable blocks *mid-file*** — bad flash sectors. FFRT error codes 1/2 = "corrupted data follows/precedes the current record." → Resynchronization: scan forward for next plausible definition/data frame; count dropped records; mark gap in provenance.
11. **Frame-shift corruption** — a bad byte causes every subsequent message to misalign (GOTOES explicitly repairs "frame-shift" and "wrong base type" cases). → Detect implausible field values as shift symptom; re-anchor on next definition message.
12. **Chained FIT files** — multiple complete FIT files concatenated in one `.fit` (legal per spec; some devices chain activity + HRV or multisport segments). → Parse all chains, emit as multi-part; never stop at first CRC.
13. **Trailing junk after final CRC** — extra bytes appended by broken tooling. → Ignore + warn (or detect a chained file, see #12).
14. **Wrapped/containerized files**: `.zip` from Garmin Connect export, `.gz`, a `.fit` inside a zip named `.fit`. → Sniff magic bytes, unwrap transparently.
15. **Wrong format in disguise** — TCX/GPX/JSON/CSV or an HTML error page saved with a `.fit` extension (download-gone-wrong). → Content sniffing, route to correct parser or clear error `NOT_FIT_FORMAT: looks like GPX`.
16. **Empty File ID + no record messages** — 2026-era Garmin firmware bug: structurally valid file with an empty `file_id` and zero records; repairable to "acceptable" but data is genuinely absent. → Distinguish "structurally broken" from "structurally fine but empty"; report what is *not* recoverable honestly.
17. **Random single-byte flips** deep in the file (storage corruption) that pass header checks but produce one absurd record. → Plausibility-gate individual records (see sections C–E) rather than trusting decode success.
18. **Duplicate file / re-export variants** — same activity exported from device vs Garmin Connect vs Strava produce different bytes (GC re-encodes). → Stable content-hash on canonical output (not raw bytes) for dedup.

## B. Protocol-level decode edge cases

19. **Data message with undefined local message type** — its definition was lost to corruption or the encoder was buggy (fitparse #21: "Got data message with invalid local message type 4"). → Skip + resync, don't abort; count occurrences.
20. **Local message type redefinition mid-file** — the same local ID (0–15) legally remapped to a different global message repeatedly. Encoders juggle 16 slots; parsers that cache definitions wrongly explode. → Full support, tested with hostile redefinition patterns.
21. **Compressed timestamp headers** — 5-bit offset, rolls over every 32 s; requires a prior full 4-byte timestamp anchor ("there must always be an initial 4-byte timestamp"). Edge cases: missing anchor, multiple rollovers between records, interaction with local type 3 / offset 31 = 0xFF padding ambiguity. → Correct rollover math; `MISSING_TIMESTAMP_ANCHOR` recovery = anchor from file_id creation time with warning.
22. **Developer data fields** (the #1 real-world parser killer):
    - `field_description` / `developer_data_id` messages missing while developer fields are referenced.
    - Developer field with **no name / null metadata** — RunScribe's Connect IQ field crashed fitparse with `'<' not supported between NoneType and str` (issue #62). → Synthesize name `dev_{index}_{field}`, keep data.
    - Same developer field ID reused by different apps in one file.
    - Known-vendor semantic mapping: **Stryd** (running power, LSS), **CORE** body temp, **Moxy** SmO2/THb, Garmin Running Dynamics via HRM pods, radar (Varia) counts, Di2/AXS gears. → Registry that promotes known dev fields to first-class typed streams. ★
23. **Unknown global message numbers** (newer profile than parser). → Preserve as `unknown_mesg_num` with raw values; never crash; forward-compatible by design.
24. **Unknown enum values** — new sports, new manufacturers, manufacturer-private enum ranges. → Pass through with `raw_value`, don't map to null.
25. **Invalid base type in definition** / field size not a multiple of base type size. → Per-field salvage: decode what divides cleanly, mark rest invalid.
26. **Sentinel "invalid" values decoded as literals** — 0xFF (255) HR, 0xFFFF (65535) power, 0x7FFFFFFF semicircles, -128 temp. Naïve pipelines produce the classic "65535 W power spike." → Sentinel-to-null is mandatory, per base type, *before* any stats.
27. **Scale/offset application** — altitude (`/5 - 500`), speed (`/1000`), semicircles→degrees (`× 180/2^31`); double-application or non-application both seen in the wild. → Canonical units in output, raw values retained on request.
28. **`enhanced_` field pairs** — `speed` (uint16) caps ~65.5 m/s scaled, `altitude` caps ~6553 m; `enhanced_speed`/`enhanced_altitude` (uint32) supersede them. Files may carry one, other, or both, disagreeing. → Prefer enhanced; reconcile; never emit both silently.
29. **Component fields & expansion** — packed fields expanding into multiple targets (e.g., legacy `compressed_speed_distance`), cycles→strides. Distance component is **12-bit and rolls over every 256 m** — must accumulate.
30. **Accumulated fields & rollover generally** — any accumulated field can wrap its base type on ultra-length activities. → Accumulator logic with wrap detection.
31. **Subfields (dynamic fields)** — field meaning switches on another field's value (e.g., `event.data` reinterpreted per `event` type). → Full dynamic-field resolution.
32. **Big-endian definition messages** — legal, rare, real (some non-Garmin devices). Mixed endianness across definitions within one file. → Per-definition endianness, tested.
33. **String fields**: missing null terminator, invalid UTF-8, emoji in workout/device names, fixed-size arrays padded with garbage. → Lossy-decode with replacement char + warning.
34. **Arrays of values in one field** (e.g., HRV `time` arrays, left_right_balance arrays) — variable length, sentinel-padded tails.
35. **64-bit ints and floats** — NaN/Inf floats in the wild. → Map to null with provenance.

## C. Temporal edge cases

36. **FIT epoch is 1989-12-31T00:00:00Z** — all timestamps are seconds since then. Off-by-epoch bugs produce 1989/1990 dates.
37. **`local_timestamp` = 1989 while `timestamp` is correct** — the infamous **Zwift bug**: Garmin Connect rejected every Zwift file because local/UTC were "too far apart." Third-party encoders routinely botch `local_timestamp`. → Validate the pair; repair mode rewrites local from UTC + inferred offset. ★ (Zwift files)
38. **Negative-timezone `time_offset` corruption** — documented Connect IQ bug producing wrapped 32-bit offsets for UTC-negative zones; requires modular arithmetic to recover. → Known-bug detector.
39. **Timestamps below the "sane" floor** (< ~2010) with plausible deltas — device never got GPS time (Geko-style "wildly stupid timestamps"). → Flag `UNRELIABLE_ABSOLUTE_TIME`, keep relative timeline, optionally re-anchor from filename/user input.
40. **Timestamps in the future** — wrong device clock pre-GPS-lock.
41. **Non-monotonic timestamps** — records out of chronological order (FFRT: "timestamps not in chronological order," auto-removed). Causes: GPS time resync mid-activity (clock jumps *backwards* after satellite lock), corruption, buggy merges. → Sort vs drop vs re-anchor = explicit policy; record the decision.
42. **Duplicate timestamps** — two+ records in the same second (sensor flushes, 1 Hz collisions, merged files). → Deterministic tie-break, no data loss.
43. **Large timestamp gaps** with four distinct meanings that must be disambiguated via event messages: (a) **smart recording** (Garmin writes only on change — up to ~25 s gaps are *normal*), (b) **auto-pause**, (c) **manual stop/resume** (stopped at café for an hour), (d) **corruption-induced gap**. The choochoo cookbook's 273 s jump = user stopped timer late. → Gap classification is a core feature; never blindly interpolate.
44. **Records written *after* timer stop** — end-of-activity metadata records minutes later. → Exclude from moving-time/stats, keep in raw.
45. **Timer event stack**: `timer start/stop_all/pause`, nested/unbalanced events, missing final stop (crash), `stop_all` without start. → Reconstruct timer state machine defensively; derive timer-time when session summary is missing/wrong.
46. **Elapsed vs timer vs moving time** — three different durations; session claims disagreeing with record-derived values. → Compute all three, reconcile, expose discrepancy.
47. **Midnight-crossing, DST-transition, and timezone-crossing activities** (flights with watch recording; DST spring-forward mid-run). Local-time math must never corrupt the UTC stream.
48. **Sub-second data** — `timestamp_ms` fractional fields on high-rate data; correlation via `timestamp_correlation` messages (Virb-style offset between system and UTC time).
49. **Ultra-length activities**: > 24 h, multi-day; uint16 duration/summary fields overflowing; > 65535 s laps.
50. **Lap/session `timestamp` semantics trap** — per FIT spec, a summary message's timestamp is when it was *written*, NOT the event end: "the timestamp should not be used to determine start or end time" — correct end = `start_time + total_elapsed_time`. Summary-First vs Summary-Last file layouts both legal (broke MyTourbook). → Never key anything off summary write-timestamps.

## D. GPS & position edge cases

51. **Null Island (0,0)** and invalid-sentinel (0x7FFFFFFF) positions interleaved with valid ones.
52. **Pre-lock garbage coordinates** — first N records at a previous location (where the device last had lock — sometimes another *country* after travel) before snapping to reality. → Detect initial-position discontinuity, trim/flag.
53. **GPS spikes / teleports** — single-record jumps implying > 200 km/h on a run (FFRT: "excessively large jump in distance"; forum repairs = "one corrupt record with strange GPS data" removed). → Speed-gated outlier rejection per sport; log removals. ★
54. **Tunnels/underpasses** — signal loss then re-acquisition with a straight-line jump; distance-from-GPS vs distance-from-sensor divergence.
55. **Urban canyon / forest drift** — plausible-but-wrong wander inflating distance (the classic "ran a 42.7 km marathon" problem). → Optional smoothing, never silent.
56. **Open-water-swim GPS** — fixes only during breathing strokes; zigzag tracks; massive over/under-distance. Sport-aware handling.
57. **Indoor activities with no GPS** but session expects distance (from accelerometer/trainer). Also **virtual GPS**: Zwift writes Watopia coordinates that don't exist on Earth — must not be "corrected," geocoded, or spike-filtered against real-world speed limits. ★
58. **Altitude**: barometric drift (start ≠ end at same physical point), rain-blocked ports (wild plunges), negative values (legit below sea level vs error), `altitude` vs `enhanced_altitude`, GPS-vs-baro disagreement, files with no altitude at all.
59. **Distance stream anomalies**: decreasing distance, distance resets to 0 mid-file, distance frozen while position moves (dead speed sensor), GPS-distance vs wheel-sensor distance divergence (wrong wheel circumference).
60. **Antimeridian ±180° crossing** and near-pole activities — naive lat/lon math breaks (bounding boxes, distance calcs).
61. **Speed inconsistencies**: `speed` field vs position-derived speed vs sensor speed; 16-bit speed saturation on fast descents (see #28).

## E. Sensor-data quality edge cases

62. **HR anomalies**: spikes to 200+ from strap static/dry contacts, optical-HR cadence lock-on (HR = running cadence), flatlined values, dropouts, 255 sentinel, HR arriving seconds late at start. → Physiologic gating (user max-HR-aware if profile present), spike interpolation as *opt-in repair* with provenance. ★
63. **Power anomalies**: 65535 sentinel spikes (see #26); genuine 2000+ W sprint vs corruption (context-dependent!); single-leg-doubled values from one-sided meters; drivetrain-estimated vs direct-force disagreement. ★
64. **Zero vs null power** — the analytics landmine: coasting = *real* 0 W; dropout = *absent*. Conflating them corrupts NP/IF-class calculations downstream. → Preserve the distinction explicitly in the schema; never fill nulls with zeros silently.
65. **Left/right balance encoding** — packed byte with a "which side" flag bit (bit 7); vendors get it wrong; 50/50 exactly = often "no data."
66. **Cadence**: crank vs wheel confusion, `fractional_cadence` add-on field, 255 sentinel, running cadence in strides-per-min vs steps-per-min (×2 ambiguity between vendors).
67. **Calibration events mid-activity** — power-meter zero-offsets producing event messages + brief garbage readings.
68. **Per-stream dropouts** (ANT+ interference): power missing for 90 s while HR/GPS continue — gap in one stream only. → Streams are independently sparse; schema must support per-stream validity masks.
69. **Duplicate sensor sources in one file** — pedals + trainer both writing power; two HR sources. → Detect, choose/expose both, don't average blindly.
70. **Dying-sensor garbage tails** — low-battery sensors emit noise before silence.
71. **Temperature**: -128 sentinel, thermal lag after leaving buildings, wrist-heating bias.
72. **HRV/RR-interval arrays** (see #34) — irregular lengths, padding, used by recovery tools; often silently dropped by parsers.

## F. Sport & mode-specific structures

73. **Pool swim**: `length` messages (active vs rest vs drill), strokes per length, distance = lengths × configured pool size — **user set 25 m but swam in 33⅓ m** (unfixable in-data, flaggable via SWOLF/pace implausibility), drill-mode lengths without stroke data, zero-length artifacts from wall push timing. ★
74. **Open-water swim**: sport-specific GPS handling (#56), distance corrections.
75. **Multisport files**: one file, N sessions + transition sessions; sport/sub_sport per session; sessions sharing or not sharing record ranges. → First-class multisport output, sessions correctly bounded. ★ (your race files)
76. **"Forgot to switch mode"**: triathlon recorded as single-sport, run recorded as bike — data-vs-declared-sport implausibility detection (optional heuristic flag, never auto-rewrite).
77. **Strength training**: `set` messages, rep counts, exercise-category enums (frequently unknown values, see #24).
78. **Treadmill runs**: accelerometer distance; **end-of-run manual distance correction** creates a single final record with a huge distance jump — legit, not a spike.
79. **Manual/summary-only activities** — session message, zero records. → Valid output with empty streams, not an error.
80. **Wrong file type uploaded**: FIT *course* files, *workout* files, *monitoring*/sleep/HRV/settings files all share the container. → Route on `file_id.type`; parse courses & workouts properly (they're inputs for other features); clear error when an activity was expected.
81. **Winter sports**: auto-detected ski runs vs lift rides (session/lap semantics differ), vertical-centric metrics.
82. **Niche modes**: dive files (Descent — depth/tank messages), golf (shot messages), jump-rope, HIIT — decode-don't-crash tier.

## G. Vendor & device quirks (fingerprint-driven handling)

83. **Zwift**: local_timestamp 1989 (#37); Watopia virtual GPS (#57); historical missing-field patterns. ★
84. **Wahoo ELEMNT/ROAM**: field-population differences from Garmin (missing enhanced fields in older firmware, lap/summary quirks). ★ (your ROAM v2)
85. **Garmin firmware-specific bugs**: Edge 1050 pre-first-record corruption (#9); "activity recorded as 2 sessions, first containing zero data"; HRM-Pro-related file corruption during save; the 2026 empty-file_id bug (#16). Device+firmware fingerprint registry with targeted workarounds. ★
86. **COROS / Suunto / Polar exports**: Polar Flow FIT exports, Suunto app exports — each with sentinel and field-coverage idiosyncrasies.
87. **Budget head units** (iGPSPORT, Bryton, Magene, XOSS): looser spec adherence, odd definition-message churn, CRC laziness (#4).
88. **Phone apps & converters**: Strava app exports, RunGap/HealthFit (Apple Watch → FIT), GoldenCheetah/GPSBabel-generated files — synthesized FIT with minimal messages, no events, sometimes no session.
89. **Trainer platforms**: TrainerRoad, Rouvy, MyWhoosh — power-file conventions, ERG-mode artifacts (perfectly flat power = legit).
90. **Connect IQ data fields** writing malformed developer metadata (#22) — RunScribe et al.
91. **Ancient formats at the door**: SRM (.srm), PowerTap (.pwx), Polar (.hrm) — explicitly out of FIT scope but the intake layer should identify and route/reject them by name.

## H. Semantic validation & summary reconciliation

92. **Session totals vs record-derived totals** — distance, elapsed/timer time, calories, avg/max power/HR disagree with the streams. → Always compute independently; emit both + `discrepancy` block; configurable trust policy.
93. **avg > max** in summaries; negative totals; impossible VO2/calorie values.
94. **Lap coverage defects**: laps not covering all records, overlapping laps, lap distances not summing to session, zero-duration laps (double lap-button press). ★
95. **Missing session** (crash before summary written) → rebuild session from records — the core "repair" everyone needs (FitFileLab: "recomputes missing summaries").
96. **Missing activity message** / missing final stop event → synthesize.
97. **Zero-duration session with records present**; movement with zero distance; distance with zero movement.
98. **Units sanity**: total ascent 10× plausible (baro glitch), pace faster than world record for the distance — plausibility library per sport.

## I. Target-platform acceptance quirks (repair-output validation)

99. **Garmin Connect stricter than Strava** — documented cases of files Strava accepts and GC rejects (and the reverse). "Valid" is platform-relative. → Validation profiles: `strict-spec`, `garmin-connect`, `strava`.
100. **"Duplicate activity" rejection** — platforms dedup on timestamps/content; repaired file must either preserve identity (re-upload after delete) or be deliberately distinct.
101. **Size limits** — oversized FIT from 1 s-recording ultra rides exceeding upload caps (GOTOES ships a whole "Shrink FIT" tool). → Optional downsampling with stated policy.
102. **Minimum-viable-file requirements** per platform (file_id completeness, event presence) for synthesized/repaired output.

## J. Privacy & PII surface (parser responsibility, often forgotten)

103. **Embedded PII**: device serials, user profile messages (weight, gender, birth year, HR zones, FTP), and **start/end coordinates = home address**. → `--strip-pii` / privacy-zone trimming as first-class options; document what the file leaks.
104. **Position obfuscation interplay** — files already trimmed by Strava privacy zones (missing start/end) shouldn't trigger "truncated" heuristics.

---

## Parser behavior contract (what the taxonomy implies)

- **Three modes**: `strict` (spec-lawyer, fail fast), `lenient` (default: recover, warn), `forensic` (maximum salvage, everything annotated).
- **Never lose data silently**: every drop, repair, interpolation, and reinterpretation lands in a `provenance[]` block on the output (`"removed 2 records: GPS speed 412 km/h"`, `"rebuilt session from 8,412 records"`).
- **Errors written for agents**: machine-parseable code + human sentence + suggested flag (`FIT_TRUNCATED: file ends mid-record at byte 190,212; rerun with --recover to salvage ~94%`).
- **Deterministic**: same input bytes → byte-identical canonical JSON. Agents and CI depend on it.
- **Every item above = at least one corpus file** with a committed expected-output snapshot. Sources: your own archive (★ items), the repair-tool forum threads (users post broken files publicly with Dropbox links), synthetic corruption of clean files (truncate at every byte offset = fuzz-lite), and a community "donate your broken file" page — which doubles as an acquisition channel.

## Priority tiers for v0

- **Tier 1 (launch blockers)**: 2, 4, 9, 10, 19, 21, 22, 26, 28, 37, 41, 43, 50, 53, 64, 75, 92, 95.
- **Tier 2 (fast follow)**: 11–16, 23–25, 29–31, 39, 45–47, 51–52, 57–59, 62–63, 68, 73, 78–80, 94, 99–101.
- **Tier 3 (depth moat)**: everything else — each one a blog post, a corpus file, and an SEO/agent-search landing page ("FIT file local_timestamp 1989 fix").
