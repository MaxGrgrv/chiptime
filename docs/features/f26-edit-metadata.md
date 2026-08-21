# Feature: F26 — `edit`: metadata surgery with validated round-trip

> Status: CRITIQUED

## Purpose

Users routinely need to change *what a file says about itself* — not its
measurements. Three edits dominate demand (evidence: `docs/internal/research-fit-jobs-2026-08.md`):

1. **Sport / sub-sport** — an activity recorded as the wrong type. Platform
   "edit activity" UIs change only the platform's own database; the file
   still says the wrong thing, so every re-export and re-import carries the
   error forward. File-level editing is the only durable fix.
2. **Device identity** (manufacturer / product) — trainer-app rides that a
   platform won't count toward training load or badges because of who the
   file claims recorded it. The documented workaround costs users ~90
   minutes of SDK + CSV hand-editing; chiptime's encoder makes it one call.
3. **Time shift** — timezone mistakes, dead-clock power-on dates, and
   aligning two files before a future merge (F30).

The differentiator is not the edit; it is the **validated round-trip**: an
edited file that platforms still accept. chiptime already owns every piece
(lossless message layer + canonical encoder + strict self-check + platform
validators); F26 composes them behind one verb.

## Context Check
- [x] Reviewed docs/INDEX.md for existing features
- [x] Reviewed docs/architecture/OVERVIEW.md for architectural fit
- [x] Reviewed docs/dependencies/DEPENDENCY_MAP.md for conflicts
- [x] Reviewed docs/PRD.md for scope and principles alignment
- [x] Reviewed docs/edge-case-taxonomy.md for related edge cases
- [x] No duplication with existing features (F12 encoder writes; F13 repair
      *restores*; F26 *changes* — first user-directed write path)

### ⚠ Scope boundary — PRD non-goal collision (must be resolved in critique)

PRD §5 Non-goals states: *"No auto-rewrite of declared sport, ever (flag
implausibility instead)."*

F26 does not violate this, but the wording must be sharpened or the feature
is out of scope on a literal reading. The distinction:

| | Who decides | chiptime's role |
|---|---|---|
| **Forbidden (still)** | chiptime infers "this looks like a run, not a hike" and rewrites | Inference-driven mutation — never |
| **F26 (proposed)** | the user states `--sport running` | Executes explicit instruction, records it in provenance |

Proposed PRD amendment: *"No auto-rewrite of declared sport, ever — the
parser never infers intent and never mutates on its own. User-directed
edits (F26) are explicit, opt-in, and recorded in provenance."*

The same clause needs a second amendment: the analytics non-goal ("no
analytics beyond reconciliation") was superseded by M2.7 (ADR-0008) and is
now stale — fix in the same pass.

## Taxonomy Coverage

| Taxonomy item # | Summary | Corpus case(s) planned |
|---|---|---|
| 24 | Unknown enum values must pass through, never be nulled | `edit/unknown-enum-preserved` |
| 37 | `local_timestamp` vs `timestamp` pairing (Zwift 1989 class) | `edit/time-shift-local-pair` |
| 47 | Local-time math must never corrupt the UTC stream | `edit/time-shift-local-pair` (same case, both assertions) |
| 83 | Zwift/trainer-file device identity | `edit/device-identity` |

Non-taxonomy corpus cases (round-trip proofs): `edit/sport-change`.

## Requirements

1. **API**: `chiptime.edit(src, *, sport=None, sub_sport=None, manufacturer=None,
   product=None, time_shift_s=None, mode="lenient") -> EditResult`
   with `EditResult{data: bytes, provenance: list[ProvenanceEntry],
   output_strict_ok: bool, parse_result: ParseResult|None}` — deliberately
   mirroring `RepairResult` so the two write verbs feel identical.
2. **Sport edits apply everywhere sport is declared** — `sport`, `session`,
   `lap`, and `workout` messages — so the file cannot become internally
   contradictory. Unspecified `sub_sport` is set to `generic` only when the
   sport changes and the existing sub-sport is invalid for it; otherwise
   left untouched (never guessed).
3. **Device edits** rewrite `file_id.manufacturer` / `file_id.product` and
   the matching `device_info` entries for the *recording* device
   (`device_index == 0` / `creator`), never sensor entries — a heart-rate
   strap is not the file's creator. Accept both names (`"garmin"`) and raw
   numbers (`1`), because the ecosystem trades in magic numbers.
4. **Time shift** adds a signed offset to every field the profile types as
   `date_time`, and to `local_date_time` fields, preserving their relative
   spacing exactly (taxonomy #47: the UTC stream stays internally
   consistent; the local/UTC pair keeps its offset).
5. **Everything else round-trips untouched** — unknown messages, unknown
   fields, developer fields, and unknown enum values are re-encoded as-is
   (contract #6). An edit of one field must never be an excuse to drop
   another.
6. **Every edit lands in provenance** with the before/after values
   (contract #1) — new codes `SPORT_EDITED`, `DEVICE_EDITED`,
   `TIMESTAMPS_SHIFTED`.
7. **Self-check**: the output is re-parsed in `strict` mode;
   `output_strict_ok` reports the verdict, exactly as `repair` does.
8. **CLI**: `chiptime edit FILE -o OUT [--sport S] [--sub-sport S]
   [--manufacturer M] [--product P] [--time-shift ±SECONDS|±HH:MM]
   [--validate PLATFORM]`. Exit 64 when no edit flag is supplied (an
   "edit" that changes nothing is a usage error, not a silent copy).
9. **No-op safety**: editing a field to its current value is a no-op with a
   provenance note, not a rewrite claim.

## Acceptance Criteria
- [ ] `edit/sport-change`, `edit/device-identity`, `edit/time-shift-local-pair`,
      `edit/unknown-enum-preserved` corpus cases exist with committed
      expected outputs
- [ ] Round-trip proof: for each case, parse(edit(input)) equals parse(input)
      **except** the edited fields — asserted field-by-field, not by eyeball
- [ ] `output_strict_ok is True` for every edit case
- [ ] Edited files pass `validate --platform garmin-connect` where the input did
- [ ] Time shift preserves inter-record spacing exactly and keeps the
      local/UTC offset constant
- [ ] Unknown messages, developer fields, and unknown enum values survive an
      unrelated edit unchanged
- [ ] Mode behavior: `strict` refuses to edit a file that does not parse
      strictly; `lenient`/`forensic` edit what they can salvage (documented,
      since this differs from repair's always-salvage stance)

## Public API Impact
- **New**: `chiptime.edit`, `chiptime.EditResult` (top-level exports);
  `chiptime edit` CLI verb; three new provenance codes (registry → generated
  agent docs + per-code pages regenerate automatically).
- **Canonical JSON schema**: unchanged. Edits produce `.fit` bytes; the
  parse schema is untouched, so no schema version bump.

## Architectural Placement

`python/src/chiptime/edit.py` — the **write layer**, beside `repair.py`,
both consuming `decode` + `encode`. No changes to decode, semantics, or
output. The CLI verb is a thin wrapper (F11 pattern).

```
decode ─┬─► repair.py   (restore what broke)
        └─► edit.py     (change what the user names)   ← F26
              └── both: encode.py → strict self-check → validate.py
```

## Proposed Approach

1. `parse(src, mode)` for the lossless `Message` list (unknown-tolerant).
2. Build a transform pipeline: one small pure function per edit, each
   `(list[Message]) -> tuple[list[Message], list[ProvenanceEntry]]`.
   Timestamp shifting reads `kind == "date_time" | "local_date_time"`
   straight from the merged profile (98 typed fields — no hand-list to rot).
3. Re-encode with `encodable_from_message` (F12), which already preserves
   developer fields and unknown content.
4. Self-check by strict re-parse; optionally run a platform validator.
5. Return `EditResult`.

Deliberately *not* in F26: trimming (F27), scrubbing (F28), converting
(F29), merging (F30). This feature is metadata only — it never touches a
measurement.

## Dependencies
- **Depends on:** F3 (decode), F12 (encoder), F13 (repair — pattern + result
  shape), F14 (validation, optional self-check), F11 (CLI)
- **Depended on by:** F27/F28/F30 (share the transform+re-encode skeleton),
  M3 (TS twin must match)

## Critique & Assessment

### Necessity — PASS
Demand is documented across two independent research sweeps, and the
workaround users actually perform (SDK + CSV hand-editing, ~90 min) is
evidence of unpriced demand. No existing feature covers it: F13 `repair`
restores what broke; F26 changes what the user names. Not building it
leaves chiptime a read-mostly library while every high-frequency user job
is a write.

### Placement — PASS
`edit.py` beside `repair.py` in the write layer is correct: same inputs
(decode), same output path (encode → strict self-check), no new coupling.
Rejected placement: folding edits into `repair(..., sport=…)` — it would
conflate "restore what broke" with "change what I asked", and the two have
opposite honesty semantics (repair must never change intent; edit must).

### Empirical approach validation (run during critique, not assumed)
Identity re-encode (`parse → encode → parse`, field-by-field comparison)
over 33 corpus cases including the real-file tier:

- **32/33 lossless**, including compressed timestamps, accumulators,
  big-endian, developer fields, unknown enums, and a 72,924-message
  multisport file. The proposed approach is sound at scale.
- **1 failure — a pre-existing shipped defect, not an F26 defect**:
  `temporal/timestamp-as-bytes` raises `EncodeError: field 253:
  1149238800 bytes exceeds size 4`. Root cause: decode *reinterprets*
  field 253 declared as `byte[4]` into a real timestamp (F22), but
  `encodable_from_message` re-encodes against the original wire type.
  **`chiptime repair` fails on this file class today** (verified in
  v0.4.1) — any user with a Xiaomi-pipeline file cannot repair it.

### ⛔ Required change 1 — fix the encoder defect first
F26's entire promise is a validated round-trip; it cannot ship on a
foundation that raises on a committed corpus case. Fix in `encode.py`:
when a field was reinterpreted during decode, re-encode it in its
**semantic** type (canonical wire form per ADR-0006) rather than the
broken source type, with provenance. This is a bug fix that stands alone,
benefits `repair` immediately, and warrants its own patch release.

### ⛔ Required change 2 — PRD amendments (two, both stale-doc fixes)
1. Sharpen the sport non-goal to separate inference (forbidden) from
   user-directed edits (F26, explicit + provenanced), per the spec's scope
   table. Without this the feature is out of scope on a literal reading.
2. The analytics non-goal ("no analytics beyond reconciliation") was
   superseded by M2.7/ADR-0008 and is now wrong. Fix in the same pass.

### ⛔ Required change 3 — drop the inference in requirement 2
The spec proposes setting `sub_sport` to `generic` "when the existing
sub-sport is invalid for the new sport". That is chiptime deciding intent
— exactly what the non-goal forbids, smuggled in as a convenience.
**Revised**: never touch `sub_sport` unless the user names it; if the
resulting pair is implausible, emit a *warning* (flag, don't fix — the
house rule for physiological data applies equally to metadata).

### Risks
- **Time-shift overflow**: FIT timestamps are uint32 seconds from
  1989-12-31. A large negative shift underflows below the epoch; a large
  positive one exceeds `0xFFFFFFFE` (and `0xFFFFFFFF` is the invalid
  sentinel — shifting *onto* the sentinel would silently null a real
  timestamp, a contract #4 violation). **Mitigation**: bounds-check every
  shifted value; refuse the whole edit with a coded error naming the first
  offending field. Never clamp silently.
- **Blast radius**: `edit.py` is additive; the only shared-code change is
  the encoder fix, which is corpus-gated in both directions (repair cases
  and new edit cases both exercise it).
- **Scale**: verified on 72,924 messages; re-encode is linear and already
  exercised by repair.

### Determinism / contract check
- Silent loss: none — every edit emits provenance; the identity test
  above is the proof that untouched fields survive. Add it as a permanent
  test, not a one-off critique artifact.
- Determinism: encode path is already byte-deterministic (corpus-gated);
  edits introduce no ordering, floats, clock, or randomness.
- Sentinels/zero-vs-null: untouched by metadata edits, except the
  time-shift-onto-sentinel hazard above (now guarded).
- Modes: specified. Note `strict` refuses to edit a non-strict file —
  deliberately unlike `repair`, because editing implies the user believes
  the file is sound.
- Errors: three new provenance codes + one new error code for the
  overflow guard (`TIME_SHIFT_OUT_OF_RANGE`), all registry-backed.
- Corpus: 4 cases planned, one per taxonomy claim. Adequate.

### Simplification
- **Cut `--validate PLATFORM` from the CLI** (deferred): `chiptime
  validate` already exists and composes fine (`chiptime edit … && chiptime
  validate …`). One flag less, zero capability lost.
- Considered and rejected as over-cutting: dropping time-shift to a later
  feature. It is the one edit that touches every message type, so it is
  what proves the transform pipeline generalizes for F27/F28/F30.
- The 20%/80% version is exactly requirements 1–3 (sport, device, time)
  with provenance and the self-check — which is what remains after the
  cuts above.

### Final decision: **APPROVE** — conditional on required changes 1–3
Build order: encoder fix (+ its own patch release) → PRD amendments →
F26 proper. The identity round-trip harness becomes a permanent test.

## Related
- ADR: candidate — "user-directed edits vs inference" (see scope boundary above)
- Research: `docs/internal/research-fit-jobs-2026-08.md` (internal)
- Implementation: `docs/implementation/f26-edit-metadata.md`
