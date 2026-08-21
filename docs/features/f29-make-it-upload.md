# Feature: F29 — `doctor`: why won't this upload, and what do I run?

> Status: DONE

## Purpose

The sharpest unserved pain found in the forum research
(`docs/internal/research-forums-2026-08-21.md` §1) is not "my file is
broken" — it is:

> *"I repaired it, every other platform accepts it, and Garmin Connect
> still refuses. Nothing tells me why."*

Recurring independently 2022→2026 across three communities, unsolved.
Confirmed from the writer's side too: SDK re-encoding drops `file_id` /
`device_info`, so Strava rejects the result, and practitioners fall back to
a deliberately **lossy** FIT→GPX→FIT round trip purely to win acceptance.

chiptime already holds most of the answer — canonical re-emit with an
identity round-trip (0.4.2), platform validation profiles (F14), and four
write verbs. What is missing is the verb that *joins them up*: something a
user runs on a file that won't upload which says, in one screen, what is
wrong, which platform cares, and **the exact command that fixes it**.

That is contract #5 ("errors are written for agents: code + sentence +
suggested flag") applied at whole-file scale, for humans.

Two supporting pieces ship with it:

1. **A validator gap**: the community-reverse-engineered Garmin Connect
   acceptance checklist includes a **timer stop event**; our profile checks
   for `event` messages but never that the activity is actually *stopped*.
2. **`edit --total-distance`**: treadmill calibration does not travel with
   the file — the durable fix is editing the recorded distance, demand rated
   "many", and a single-purpose website exists for nothing else. Our `edit`
   verb covers sport, device, and time but not distance.

## Context Check
- [x] docs/INDEX.md — F14 validates; F13 repairs; nothing *triages*
- [x] docs/architecture/OVERVIEW.md — CLI/composition layer over existing verbs
- [x] docs/dependencies/DEPENDENCY_MAP.md — composes F13/F14/F26; no cycles
- [x] docs/PRD.md — squarely the "errors written for agents" invariant
- [x] docs/edge-case-taxonomy.md — #95 (missing session), #50, #37 all surface here
- [x] No duplication — `validate` reports findings; `doctor` interprets them and prescribes

## Taxonomy Coverage

| Taxonomy item # | Summary | Corpus case(s) |
|---|---|---|
| 95 | Missing session/activity summaries | existing `reconcile/no-session-rebuild` |
| 41 | Missing timer stop / unterminated activity | existing `temporal/missing-final-stop` (now asserted through the GC validator too) |

No new corpus inputs; assertions run against committed cases.

## Requirements

1. **`doctor(src, *, platform="garmin-connect", mode="lenient") -> Diagnosis`**
   with `Diagnosis{will_upload: bool, findings, remedies, parse_summary}`.
2. **Every blocking finding maps to a remedy** — a concrete command string
   (`chiptime repair FILE -o fixed.fit`) plus a one-line reason. A finding
   with no known remedy says so honestly rather than inventing one.
3. **Remedies are ordered and deduplicated**: if three findings all resolve
   with `repair`, the user is told to run it once.
4. **`chiptime doctor FILE [--platform P] [--json]`**; exit 0 when the file
   should upload, 2 when remedies exist, 3 when nothing can be done.
5. **Validator addition**: `VAL_GC_NO_TIMER_STOP` when an activity carries
   timer events but never a `stop`/`stop_all` — the checklist item we miss.
6. **`edit --total-distance METRES`**: set the activity's true distance.
   Records are scaled proportionally so the stream and the summary agree
   (a summary that contradicts its own records is the lie F27 exists to
   prevent), and **speed is scaled by the same factor** so the file stays
   internally consistent. Provenance records the factor.
7. Both new paths keep the existing guarantees: strict self-check on write,
   provenance on every change.

## Acceptance Criteria
- [ ] `doctor` on a truncated crash file reports the blocking findings and
      prescribes `repair`; after running that command, `doctor` reports the
      file will upload — asserted end-to-end in one test
- [ ] `VAL_GC_NO_TIMER_STOP` fires on `temporal/missing-final-stop` and not on clean files
- [ ] Remedies are deduplicated and ordered (repair before cosmetic edits)
- [ ] `--json` output is deterministic and machine-parseable
- [ ] `edit --total-distance` scales records + speed + summaries consistently;
      a re-parse shows declared == derived distance (no new lie)
- [ ] Exit codes: 0 clean, 2 fixable, 3 hopeless
- [ ] Files with no known remedy say so rather than suggesting something useless

## Public API Impact
- **New**: `chiptime.doctor`, `Diagnosis`, `Remedy`; CLI verb `doctor`;
  `edit(total_distance_m=…)` parameter and `--total-distance` flag;
  validator code `VAL_GC_NO_TIMER_STOP`; provenance `DISTANCE_RESCALED`.
- **Canonical JSON schema**: unchanged.

## Architectural Placement
`python/src/chiptime/doctor.py` — a thin composition layer over `parse`,
`validate`, and the write verbs. It owns no parsing logic of its own; the
finding→remedy table is its entire substance.

## Proposed Approach
1. Parse once; run the platform profile.
2. Map findings → remedies through a static table (code → remedy template).
3. Deduplicate remedies preserving priority order.
4. Render human or JSON output.

## Dependencies
- **Depends on:** F13 repair, F14 validate, F26 edit, F11 CLI
- **Depended on by:** the "make it upload" article; M3

## Critique & Assessment

### Necessity — PASS, and it is mostly *surfacing*, not building
The rarest kind of feature: the capability already exists and the market
has been asking for it for four years without knowing we have it. Most of
the work is a finding→remedy table and a verb name.

### Empirical validation — the core promise holds
Ran the claim `doctor` will make ("this file will not upload; run repair;
then it will") against four rejected files:

| File | GC errors before | after `repair` |
|---|---|---|
| `structural/truncated-mid-record` | 1 | **0** |
| `reconcile/no-session-rebuild` | 3 | **0** |
| `temporal/missing-final-stop` | 3 | **0** |
| real `zwift-in-progress` | 1 | **0** |

The prescription is not aspirational — it is measured. The end-to-end
assertion (validate → repair → validate) becomes a permanent test so the
advice can never silently rot.

### ⛔ Required change — the timer-stop check must be a WARNING, not an error
The spec proposed `VAL_GC_NO_TIMER_STOP` as a blocking error on the strength
of a community-reverse-engineered checklist. Our validator profiles encode
*observed* platform behaviour; this rule has a single second-hand source and
is not in any documentation. Shipping it as an error would manufacture false
rejections for files Garmin Connect actually accepts — turning a helpful
tool into a liar in the one place users trust it most.

Ship it as a **warning** whose text names its provenance ("reported to be
required"), and promote it to an error only if a real file proves it.
Measurement supports the caution: on the cases tested it never changes a
verdict, because files missing a stop event were already failing on
session/lap/activity grounds.

### Risks
- **Wrong prescriptions are worse than none.** A remedy table that says
  "run repair" for a problem repair cannot fix destroys trust faster than
  silence. Mitigation: findings with no known remedy render as "no automatic
  fix" and say what to inspect; the table is small and each entry is tested.
- **Distance rescaling edits measurements.** It is user-directed and
  provenanced (same footing as `trim`), but it must scale the record stream,
  speed, and the summaries **together** — scaling the total alone would
  produce exactly the self-contradicting file F27 exists to prevent.
- Blast radius: `doctor` is read-only composition; the only shared change is
  one added validator warning.

### Contract check
- Silent loss: `doctor` writes nothing; `edit --total-distance` provenances
  the scale factor.
- Determinism: static table, sorted remedies, no clock.
- Errors: exit codes 0/2/3 documented; JSON output stable.
- Modes: inherited from the read.
- Corpus: no new inputs; existing cases carry the assertions.

### Simplification
- **Cut**: auto-fix mode (`doctor --fix`). Prescribing and executing are
  different levels of consent, and chaining verbs by hand is one line. If
  users ask, it is trivial to add later. → BACKLOG.
- **Cut**: multi-platform diagnosis in one run. One platform per invocation
  keeps the output readable and the exit code meaningful.

### Final decision: **APPROVE** — conditional on the warning-not-error change

## Related
- Research: `docs/internal/research-forums-2026-08-21.md` §1, §6 (internal)
- Implementation: `docs/implementation/f29-make-it-upload.md`
