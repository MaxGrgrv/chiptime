# chiptime — Product Requirements & System Design

> Status: **AGREED — shape locked 2026-08-17** (monorepo · MIT · encoder at M2 · Python ≥ 3.11 · name `chiptime`).
> Companion documents: [edge-case-taxonomy.md](edge-case-taxonomy.md) (the behavior backlog), [research/ecosystem-landscape.md](research/ecosystem-landscape.md), [research/licensing-conformance-naming.md](research/licensing-conformance-naming.md).

## 1. One-liner

**Recovery-grade FIT file processing.** Parse anything, lose nothing silently, explain everything. Python first, JavaScript second, one shared edge-case corpus as the conformance contract between them.

## 2. Problem

FIT is the lingua franca of fitness devices, and real-world FIT files break constantly: battery death mid-write, flash corruption, buggy firmware (Edge 1050 preamble garbage, the 2026 empty-file_id bug), and third-party encoders that botch the spec (Zwift's 1989 local_timestamp, Connect IQ fields with null metadata).

The 2026 landscape research confirms the whitespace is total:

- **Recovery is the unserved capability.** Existing tooling across the ecosystem generally stops at the first structural problem — raising, rejecting, or returning only the decoded prefix. Resynchronizing past damage and reporting what happened is the gap chiptime exists to fill.
- **No OSS library, in any language, does recovery**: no mid-file resync, no truncation salvage to valid output, no rebuilding of missing session summaries (the #1 real-world failure — records present, no session, platform rejects the upload). fit-tool explicitly lists repair as a *non-goal*.
- **Repair is locked in closed tools**: GOTOES (web, donor-gated FIT export), Fit File Repair Tool (paid Windows GUI), FitFileLab (closed web), Garmin's ActivityRepairTool.jar (compiled JAR, no source, salvages only "up to the point of corruption").
- **Nobody emits provenance, typed offset-bearing errors, gap classification, or a device-quirk registry.** The only real accumulated tolerance knowledge lives welded inside GoldenCheetah's GPL C++.
- **The official SDK is not an option as a foundation**: FIT Protocol License (non-OSI, no redistribution, anti-copyleft §2d, terminable at will), publish-only mirror that declines community PRs — including, pointedly, a rejected encoder+repair contribution.
- **No project offers matching semantics across Python and JavaScript.**

Meanwhile a new consumer class has arrived: **AI agents** parsing fitness data need deterministic output and machine-actionable errors, and today get neither.

## 3. Users & jobs

| User | Job |
|---|---|
| Sports-tech developer | "Ingest whatever users upload, never crash, know exactly what was recovered" |
| Data scientist / self-quantifier | "Turn my archive into clean, honest data — no 65535 W spikes, no zero-filled dropouts" |
| AI agent / pipeline | "Deterministic canonical JSON; errors that tell me which flag to retry with" |
| Athlete with a broken race file (via tools built on chiptime) | "Salvage my race and upload it" |
| Platform / coach software | "Validate and normalize before accepting; reconcile device claims against streams" |

## 4. Product principles — the parser behavior contract

Non-negotiable; enforced by `/critique` and `/verify` on every feature (also in CLAUDE.md):

1. **Never lose data silently** — every drop, repair, and reinterpretation lands in `provenance[]`.
2. **Deterministic** — same input bytes → byte-identical canonical JSON across runs, processes, OSes, and (eventually) languages.
3. **Three modes** — `strict` (spec-lawyer, fail fast), `lenient` (default: recover + warn), `forensic` (maximum salvage, everything annotated).
4. **Sentinels → null before any statistics**; **zero ≠ null, always** (coasting is 0 W; dropout is null).
5. **Errors are written for agents** — machine-parseable code + human sentence + suggested next step.
6. **Unknown ≠ invalid** — unknown messages/enums/fields preserved with raw values; forward-compatible by design.
7. **Every taxonomy item → at least one corpus case** with committed expected output.
8. **Honest non-recovery** — report what is genuinely absent; never fabricate.
9. **Message order is untrusted** — summary-first and summary-last layouts are both legal (the Dec-2023 Garmin change that broke parsers); nothing may assume order.
10. **Privacy is a feature** — `strip_pii` is first-class; docs state exactly what a FIT file leaks (serials, profile, home coordinates).

## 5. Scope

### v0.x (Python) — in scope
- **Intake**: content sniffing (zip/gz unwrap, TCX/GPX/HTML misnames → clear `NOT_FIT` error), chained-file splitting, routing by `file_id.type`.
- **Decode**: 12/14-byte headers (including illegal-but-seen variants), definitions/data frames, all base types, both endiannesses, compressed timestamps, developer fields (including null-metadata salvage), components/subfields/accumulators, scale/offset, enhanced-field reconciliation.
- **Recovery**: truncation salvage, mid-file resynchronization with skipped-byte accounting, frame-shift detection, preamble garbage skip, CRC triage (why it failed, not just that it failed).
- **Semantics** (activity files): canonical Activity → Sessions → Laps → Records model with columnar streams and per-stream null masks; timer state machine; gap classification (smart recording / auto-pause / manual stop / post-timer / corruption); declared-vs-derived totals with discrepancy reporting; session/activity rebuild when missing.
- **Output**: versioned canonical JSON (RFC 8785 canonicalization), provenance, diagnostics, typed errors.
- **CLI**: `parse`, `inspect`, corpus tooling.
- **Corpus**: taxonomy-driven golden cases + conformance runner (the cross-language contract).

### Staged next (order = roadmap, §10)
- **Encoder + `repair`**: emit a valid `.fit` from any salvage — the capability closed tools monopolize. Platform validation profiles (`strict-spec`, `garmin-connect`, `strava`).
- **JavaScript/TypeScript implementation** consuming the same corpus; parity gate in CI.
- Sport-specific depth (pool swim lengths, multisport bounding), device-quirk registry growth, known-vendor dev-field promotion (Stryd, CORE, Moxy, running dynamics), `[pandas]` extra.

### Non-goals
- Analytics are an **optional, separate layer** (`chiptime.metrics`, M2.7/ADR-0008) — never imported by the core,
  computed only from evidence present in the file plus thresholds the user supplies. The core's job remains handing
  over honest streams; no metric is ever estimated from a workout to fill a gap.
- No visualization, no upload clients, no cloud service, no GUI.
- No full TCX/GPX parsing — sniff, route, reject with a clear name.
- No silent "corrections" of physiological data — plausibility flags by default, repairs opt-in, everything in provenance.
- **No auto-rewrite of declared sport, ever** — chiptime never infers intent and never mutates a file on its own;
  implausibility is flagged, not fixed. User-directed edits (F26 `edit`) are a different act: explicit, opt-in,
  recorded in provenance, and never inferred. The rule is about *who decides*, not about whether bytes can change.

## 6. System design

### 6.1 Layer architecture

```
                    ┌────────────────────────────────────────────┐
                    │                  cli                       │
                    └───────────────────┬────────────────────────┘
                    ┌───────────────────▼────────────────────────┐
                    │          api  (parse / iter_*)             │
                    └───┬───────────┬───────────┬────────────┬───┘
                    ┌───▼───┐   ┌───▼───────┐   ┌───▼──────┐ ┌───▼────┐
                    │intake │   │ decode +  │   │semantics │ │ output │
                    │       │   │ recovery  │   │          │ │        │
                    └───────┘   └───┬───────┘   └──────────┘ └────────┘
                                ┌───▼───────┐
                                │ profile   │  (generated tables + dev-field registry)
                                └───────────┘
                    errors / diagnostics: leaf module, used by all
```

- **intake** — sniff magic bytes, unwrap containers, split chains, route by declared type. Everything downstream receives clean byte ranges plus intake provenance.
- **decode** — a streaming frame reader (header / definition / data / CRC frames) that is *incapable of crashing on hostile input*: every read is bounds-checked, every defect becomes a typed `Defect` value, not an exception. Owns base types, endianness, compressed-timestamp math, developer-field resolution, component expansion, scale/offset.
- **recovery** — wraps decode. On a defect: classify (truncation? frame shift? garbage block?), scan forward for the next plausible frame boundary, account for every skipped byte, resume. Strict mode converts the first defect to a raised error instead.
- **profile** — generated message/field tables (see §8 licensing) + the developer-field vendor registry. Data-only; unknown-tolerant (a stale profile never crashes decode).
- **semantics** — consumes the lossless message stream, builds the canonical model: timer state machine, gap classification, stream assembly with null masks, declared-vs-derived reconciliation, rebuild of missing summaries. Order-independent by construction (two-pass over messages).
- **output** — canonical JSON (RFC 8785), provenance assembly, dict/JSON serialization. The only module that formats anything.
- Layering rule: strictly downward dependencies; `decode` never imports `semantics`; `profile` and `errors` are leaves.

### 6.2 Key design decisions

| Decision | Choice | Why |
|---|---|---|
| Language strategy | **Twin idiomatic implementations (Python, then TS) + shared binary corpus** — no Rust core, no bindings | User-stated sequencing; zero build friction for contributors; the corpus (not code) is the contract, toml-test-style; each ecosystem gets a native-feeling API |
| Runtime dependencies (Python) | **Zero** | Maximum adoptability (stdlib `struct`, `dataclasses`); optional extras later (`[pandas]`) |
| Defects as values | Decode/recovery produce `Defect` values internally; only the API boundary converts to raised exceptions (strict) or collected errors (lenient/forensic) | Recovery cannot work if the pipeline throws; strict mode is then a thin policy, not a second code path |
| Canonical JSON | **RFC 8785 (JCS)** serialization; floats = shortest round-trip (ES6 rules); 64-bit raw values as decimal strings; UTC ISO-8601 timestamps | Cross-language byte-identical output is a solved problem if we adopt JCS; Python needs a ~100-line internal canonicalizer (zero-dep) |
| Streams | Columnar (`list` per field) with `None` for absent; row iterator as convenience | Analytics-friendly; makes zero-vs-null structurally visible; small memory |
| Semantic model always computes `derived` totals | Even when the file has a session | Reconciliation (taxonomy #92) and rebuild (#95) become the same code path; discrepancies are free |
| Message order | Two-pass semantics; nothing keyed off summary write-timestamps (taxonomy #50) | Order-independence guarantee |
| PII | `strip_pii=False` default (it's a parser), but strips deterministically when on: user_profile, serials, configurable start/end trim | Privacy as feature, not afterthought |

### 6.3 Determinism rules (testable)

- No wall-clock, no randomness, no locale, no dict-iteration luck anywhere in an output path.
- All maps sorted at serialization (JCS); all lists in file order or explicitly sorted with a documented key.
- Same bytes → same canonical JSON on CPython 3.11–3.13, macOS/Linux/Windows — CI-enforced by double-parse + cross-job hash comparison.
- `source.sha256` of input + `chiptime_schema` version embedded in output; content hash of canonical output (minus volatile source path) serves as the dedup identity (taxonomy #18).

## 7. Python SDK — proposed public signature

Package: `chiptime` on PyPI. Python ≥ 3.11. Zero runtime dependencies. Fully typed (`py.typed`).

### 7.1 Top level

```python
import chiptime

# ── the one-call happy path ─────────────────────────────────────────────
result = chiptime.parse("ride.fit")  # mode="lenient" default
result = chiptime.parse(raw_bytes, mode="strict")  # raises on first defect
result = chiptime.parse(path, mode="forensic")  # maximum salvage, everything annotated

# ── streaming / low-level ───────────────────────────────────────────────
for msg in chiptime.iter_messages("ride.fit"):  # profile-applied messages, no semantic model
    ...
for frame in chiptime.iter_frames("ride.fit"):  # lossless wire-level frames (forensics)
    ...
```

### 7.2 Signatures (v0.1 surface, `.pyi`-style)

```python
from datetime import datetime
from os import PathLike
from typing import Any, BinaryIO, Iterator, Literal

Mode = Literal["strict", "lenient", "forensic"]


def parse(
    src: str | PathLike[str] | bytes | BinaryIO,
    *,
    mode: Mode = "lenient",
    strip_pii: bool = False,
    include_unknown: bool = True,  # keep unknown messages/fields in output
    include_raw: bool = False,  # retain raw wire values alongside scaled
) -> ParseResult:
    """Parse a FIT file (or zip/gz-wrapped, or chained container).

    strict   → raise the first FitError encountered (spec-lawyer)
    lenient  → recover what's recoverable; collect errors/warnings   [default]
    forensic → aggressive resync + salvage; every byte accounted for

    In lenient/forensic, raises only OSError (I/O) — never on content.
    """


def iter_messages(src, *, mode: Mode = "lenient") -> Iterator[Message]: ...
def iter_frames(src, *, mode: Mode = "lenient") -> Iterator[Frame]:
    ...
    # Frame = FileHeader | DefinitionFrame | DataFrame | CrcTrailer | SkippedBytes


# ── result object ───────────────────────────────────────────────────────


class ParseResult:
    ok: bool  # usable output was produced
    mode: Mode
    source: SourceInfo  # sizes, sha256, container unwrapping applied
    parts: list[FitPart]  # ≥1; >1 only for chained files (taxonomy #12)
    provenance: list[ProvenanceEntry]  # every drop/repair/reinterpretation
    warnings: list[Diagnostic]
    errors: list[FitError]  # collected here in lenient/forensic; raised in strict
    recovery: RecoveryReport | None  # present when recovery engaged

    # conveniences — delegate to the primary part (first activity part, else first part)
    @property
    def file_type(self) -> str: ...  # "activity" | "course" | "workout" | "monitoring" | ...
    @property
    def activity(self) -> Activity | None: ...
    @property
    def messages(self) -> list[Message]: ...

    def to_dict(self) -> dict[str, Any]: ...
    def to_canonical_json(self) -> bytes: ...  # RFC 8785; byte-identical across runs/languages


class SourceInfo:
    path: str | None
    size_bytes: int
    sha256: str
    unwrapped: list[str]  # e.g. ["zip"] when a .fit came out of a GC export zip


class RecoveryReport:
    recovered_records: int
    estimated_total_records: int | None  # None when honestly unknowable
    bytes_read: int
    bytes_skipped: int
    resync_count: int


class FitPart:
    file_type: str
    file_id: FileId | None  # None only for the empty-file_id firmware bug (#16)
    messages: list[Message]  # lossless, unknown included
    activity: Activity | None  # populated when file_type == "activity"


# ── lossless message layer ─────────────────────────────────────────────


class Message:
    global_num: int
    name: str  # "record", or "unknown_233"
    fields: dict[str, FieldValue]
    byte_offset: int  # where this message started in the file


class FieldValue:
    value: Any | None  # scaled, unit-normalized, sentinel→None applied
    raw: Any | None  # wire value (present when include_raw=True)
    units: str | None
    developer: DevFieldOrigin | None  # set for developer fields (app id, vendor mapping)


# ── canonical semantic model (activity files) ──────────────────────────


class Activity:
    sessions: list[Session]  # multisport-first: always a list, transitions included
    events: list[Event]
    gaps: list[Gap]
    device: DeviceInfo | None
    athlete: AthleteProfile | None  # None when absent or strip_pii=True


class Session:
    sport: str
    sub_sport: str | None
    start_time: datetime | None  # UTC, tz-aware
    laps: list[Lap]
    lengths: list[Length]  # pool swimming
    records: Records
    declared: Totals | None  # what the file claimed (None → was missing)
    derived: Totals  # always recomputed from records
    discrepancies: list[Discrepancy]  # declared vs derived, field by field
    rebuilt: bool  # True when session was synthesized from records (#95)


class Totals:
    elapsed_time_s: float | None
    timer_time_s: float | None
    moving_time_s: float | None
    distance_m: float | None
    ascent_m: float | None
    descent_m: float | None
    calories_kcal: float | None
    avg: dict[str, float]  # per-stream averages (null-aware, never sentinel-polluted)
    max: dict[str, float]


class Records:
    n: int
    time: list[datetime]  # UTC; sub-second via timestamp_ms merged in

    def stream(self, name: str) -> Stream | None: ...
    def streams(self) -> dict[str, Stream]: ...
    def rows(self) -> Iterator[dict[str, Any]]: ...  # row-oriented convenience view


class Stream:
    name: str  # "power", "heart_rate", "position_lat", "dev_stryd_lss", ...
    units: str | None
    values: list[float | int | None]  # None = absent (sentinel or dropout); 0 is a real zero
    source: str  # "native" | "developer:<vendor-or-app>"


class Gap:
    start: datetime
    end: datetime
    duration_s: float
    kind: Literal[
        "smart_recording", "auto_pause", "manual_stop", "post_timer", "corruption", "unknown"
    ]
    evidence: str  # human sentence: which events/heuristics decided it


# ── provenance, diagnostics, errors ────────────────────────────────────


class ProvenanceEntry:
    code: str  # stable id: "RESYNC_SKIPPED_BYTES", "SESSION_REBUILT", ...
    action: Literal["dropped", "repaired", "synthesized", "reinterpreted", "ignored"]
    scope: str  # "file" | "part[0]" | "record[1423]" | "stream.power" | ...
    detail: str  # "skipped 212 bytes at offset 190,212 after CRC-invalid frame"
    byte_offset: int | None
    data: dict[str, Any]  # machine-readable specifics (counts, before/after)


class Diagnostic:
    code: str
    detail: str
    scope: str


class FitError(Exception):
    code: str  # "FIT_TRUNCATED", "NOT_FIT_FORMAT", ...
    detail: str  # human sentence with numbers
    byte_offset: int | None
    suggestion: str | None  # 'rerun with mode="lenient" to salvage ~94% of records'


class NotFitError(FitError): ...  # sniffed as GPX/TCX/HTML/zip-of-something-else


class EmptyFileError(FitError): ...


class HeaderError(FitError): ...


class TruncatedError(FitError): ...


class CrcMismatchError(FitError): ...


class ProtocolError(FitError): ...  # framing/definition-level defects
```

### 7.3 Behavior examples (normative)

```python
# Truncated Zwift crash file, lenient (taxonomy #2):
r = chiptime.parse("inProgressActivity.fit")
assert r.ok
r.recovery  # recovered_records=8412, estimated_total_records=8900, resync_count=0
r.activity.sessions[0].rebuilt  # True — session synthesized from records
r.provenance[-1].code  # "SESSION_REBUILT"

# Same file, strict:
chiptime.parse("inProgressActivity.fit", mode="strict")
# → TruncatedError(code="FIT_TRUNCATED",
#     detail="file ends mid-record at byte 190,212 of declared 202,880",
#     suggestion='rerun with mode="lenient" to salvage ~94% of records')

# 65535 W sentinel spike (taxonomy #26): never visible.
power = r.activity.sessions[0].records.stream("power")
assert 65535 not in power.values  # sentinel decoded → None, present in provenance? No —
# sentinel→None is normal decoding, not a repair; no noise.

# Zero vs null (taxonomy #64):
power.values[102] == 0  # rider coasting — real zero
power.values[315] is None  # ANT+ dropout — absent

# GPX renamed to .fit (taxonomy #15), lenient:
r = chiptime.parse("actually_a_gpx.fit")
r.ok is False
r.errors[0].code  # "NOT_FIT_FORMAT"
r.errors[0].detail  # "content is GPX (XML with <gpx> root)"
```

### 7.4 CLI

```
chiptime parse <file> [--mode strict|lenient|forensic] [--json | --summary]
                      [--strip-pii] [--include-raw] [-o out.json]
chiptime inspect <file> [--frames] [--from-offset N]      # wire-level forensics view
chiptime corpus run|add|regen                             # dev tooling (conformance)
# roadmap (with encoder): chiptime repair <in> -o <out.fit> [--platform garmin-connect|strava]
```

Exit codes (agent contract): `0` ok · `2` recovered with data loss (details on stderr as JSON) · `3` unusable input · `4` not a FIT file · `64` usage error.

### 7.5 Canonical JSON sketch (schema `chiptime/1`)

```jsonc
{
  "chiptime_schema": 1,
  "source": {"sha256": "…", "size_bytes": 202880, "unwrapped": []},
  "ok": true,
  "mode": "lenient",
  "parts": [{
    "file_type": "activity",
    "file_id": {"manufacturer": "zwift", "time_created": "2026-07-30T17:02:11Z", "…": "…"},
    "activity": {
      "sessions": [{
        "sport": "cycling", "start_time": "2026-07-30T17:02:12Z", "rebuilt": true,
        "declared": null,
        "derived": {"elapsed_time_s": 4211.0, "distance_m": 32882.4, "…": "…"},
        "discrepancies": [],
        "records": {
          "n": 8412,
          "time": ["2026-07-30T17:02:12Z", "…"],
          "streams": {
            "power": {"units": "W", "source": "native", "values": [212, 0, null, "…"]}
          }
        },
        "laps": ["…"]
      }],
      "gaps": [{"start": "…", "end": "…", "duration_s": 273.0, "kind": "manual_stop",
                 "evidence": "timer_stop_all at 17:44:03, timer_start at 17:48:36"}]
    },
    "messages": "…(lossless, incl. unknown_*, when requested)…"
  }],
  "recovery": {"recovered_records": 8412, "estimated_total_records": 8900,
                "bytes_read": 190212, "bytes_skipped": 0, "resync_count": 0},
  "provenance": [
    {"code": "TRUNCATED_TAIL_SALVAGED", "action": "repaired", "scope": "file",
     "byte_offset": 190212, "detail": "file ends mid-record; salvaged 8412 complete records",
     "data": {"declared_size": 202880, "actual_size": 190212}},
    {"code": "SESSION_REBUILT", "action": "synthesized", "scope": "part[0].session[0]",
     "detail": "no session message present; totals derived from 8412 records", "data": {}}
  ],
  "warnings": [], "errors": []
}
```

Numbers: JCS/ES6 formatting; 64-bit raw values serialized as decimal strings; all timestamps UTC ISO-8601 `Z`.

## 8. Profile & licensing strategy (hard constraints)

Per [research/licensing-conformance-naming.md](research/licensing-conformance-naming.md):

- Library license: **MIT** (decided 2026-08-17; fitparse/fitdecode precedent).
- **Never** depend on `garmin-fit-sdk`/`@garmin/fitsdk`; **never** commit Profile.xlsx, any SDK file, or official SDK sample `.fit` files.
- `scripts/generate_profile.py` converts a locally downloaded SDK profile into `src/chiptime/profile/generated.py` (our shape, provenance header with SDK version + date). Only generated output is committed — the fitparse/fitdecode pattern, 14 years unchallenged.
- No published benchmarks against other libraries (positioning risk); internal QA oracles only. The official SDK is never benchmarked in any form (license §2f).
- README carries: non-affiliation disclaimer + "FIT and Garmin are trademarks of Garmin Ltd."
- Profile staleness is survivable by design: unknown messages/fields always decode as `unknown_*` (contract #6).

## 9. The corpus — conformance contract

Layout (patterns from toml-test + JSON-Schema-Test-Suite; see research):

```
corpus/
  cases/<category>/<fault-named-slug>/
      input.fit             # possibly deliberately corrupt; generated, never hand-edited
      expected.json         # canonical output (chiptime/1) — the snapshot
      case.json             # metadata: taxonomy refs, tier, grade, generator + params, source
  seeds/                    # clean donor files (own archive ★, sanitized w/ strip-pii)
  tools/                    # corruption generators: truncate-sweep, bit-flip, frame-shift,
                            # header surgery, chain-builder, synthetic encoders
  MANIFEST.json             # versioned case list (subsetting + suite versioning)
```

`case.json` (graded expectations — FIT failure isn't binary):

```jsonc
{
  "taxonomy": [2, 95],
  "tier": 1,
  "expect": "partial",                    // "ok" | "partial" | "reject"
  "error_class": null,                    // e.g. "NOT_FIT_FORMAT" for reject cases
  "modes": {"strict": "reject:FIT_TRUNCATED", "lenient": "partial", "forensic": "partial"},
  "generator": {"tool": "truncate.py", "args": {"seed": "seeds/zwift-ride-01.fit", "at": 190212}},
  "source": "synthetic",                  // synthetic | own-archive | donated (with consent note)
  "notes": "battery-death truncation mid-record"
}
```

Rules:
- Every taxonomy item ≥ 1 case (contract #7); `/doc-check` audits coverage per tier.
- Expected outputs are reviewed snapshots; changing one requires an explanation in the PR/implementation doc.
- Acquisition flywheel: own archive (★ items) → synthetic corruption of seeds (truncate-at-every-offset = fuzz-lite) → public "donate your broken file" page (also an adoption channel).
- Consumption: Python via a thin pytest loader now; JS via a vitest loader at M3; optional stdin/stdout subprocess protocol later for third-party implementations.

## 10. Quality bars & metrics

- **Determinism CI**: parse twice in separate processes + across OS matrix; canonical bytes must match.
- **Fuzz-lite in CI**: truncate a seed at every byte offset — decode must never raise (lenient), never hang, never emit invalid canonical JSON. Property tests (Hypothesis) on decode primitives.
- **Robustness statement** (self-referential only): every corpus case decodes without a crash; recovery numbers cite chiptime's own behavior, never other libraries'.
- **Performance**: informational benchmark, not a gate at v0.1 (pure Python; typical 1 MB ride target < 200 ms on laptop hardware; revisit after correctness lands).
- **Adoption signals**: PyPI downloads, GitHub issues that arrive as "here's a broken file" (each becomes a corpus case — the flywheel working).

## 11. Roadmap

| Milestone | Deliverable | Contents |
|---|---|---|
| **M0** ✅ | Shape agreement | Done 2026-08-17 |
| **M1** ✅ | 0.1.0 tagged 2026-08-18 | Shipped: all Tier-1 (18/18), 56 cases, determinism + fuzz gates. PyPI/npm registration = maintainer action pending |
| **M2** ✅ | 0.2.0 tagged 2026-08-18 | Shipped: encoder, repair, validate profiles, CRC triage, Tier-2 batch, internal robustness gate: 3279 messages, 0 crashes across the corpus |
| **M2.5** ✅ | 0.3.0 tagged 2026-08-18 | From the 66-file soak (0 contract violations): F17 soak fixes (FIT_NO_CONTENT for empty shells #16, sport-aware DISTANCE_FROZEN, repair drops implausible local_timestamp), F18 full profile generation (maintainer SDK local), F19 real-file corpus promotion (own files only, PII policy; NEVER SDK samples), F20 perf pass (~1s/MB → target 3-5x), F21 swim/HRV depth (#72) |
| **M2.6** ✅ | shipped 2026-08-18 | Ecosystem-issue hardening: publicly reported FIT parsing failure modes surveyed → 30 classes → 21 pre-handled, 9 fixed (incl. hr event_timestamp_12 12-bit expansion) |
| **M2.7** ✅ | 0.4.0 tagged 2026-08-18 | Analytics layer (ADR-0008): F23 sport profiles + pacing (profiles-as-data, inverse-safe pace, Concept2 bridge, splits), F24 interval/structure detection (evidence ladder, honest bands), F25 insights + load + `chiptime analyze` (basis strings, omissions, TRIMP coverage guard, fitness/fatigue/form EWMA) |
| **M2.8** ◐ | in progress | File surgery — the write verbs users actually ask for: F26 `edit` (metadata) ✅ 0.5.0; F27 `trim` (crop + rebuild) ✅ 0.6.0; F28 `reveal`/`scrub` (privacy) ✅ 0.7.0; F29 `doctor` + calibration ✅ 0.8.0 (reprioritised from forum research); F30 merge, convert queued |
| **M3** | JS/TS `chiptime` on npm | Twin implementation consuming the same corpus; parity gate in CI; browser + Node |
| **M4+** | Depth moat | Tier-3 items; device-quirk registry; dev-field vendor registry (Stryd, CORE, Moxy…); per-edge-case docs pages (SEO/agent-search: "FIT local_timestamp 1989 fix"); donation page; `[pandas]` extra |

## 12. Shape decisions — resolved 2026-08-17

1. **Repo strategy**: **monorepo** — `corpus/` + `python/` + `js/` + `docs/` in one repo. Corpus and implementations evolve atomically; revisit a standalone corpus repo only if third-party implementations materialize.
2. **License**: **MIT** (LICENSE at root).
3. **Encoder timing**: **M2 fast-follow** — 0.1 ships decode + recovery + canonical JSON; 0.2 adds encoder + `repair` + platform validation profiles.
4. **Python floor**: **3.11**.
5. **Name**: `chiptime` everywhere (PyPI, npm, import name); both registry names free as of 2026-08-17 — register at M1.
