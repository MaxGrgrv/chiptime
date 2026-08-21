# Implementation: F26 — `edit`: metadata surgery with validated round-trip

> Spec: [features/f26-edit-metadata.md](../features/f26-edit-metadata.md) · 2026-08-21 · Ships in 0.5.0

## What was built

`python/src/chiptime/edit.py` — `edit(src, *, sport, sub_sport, manufacturer,
product, time_shift_s, mode) -> EditResult`, plus the `chiptime edit` CLI verb.
Three transforms, each a pure `list[Message] -> (list[Message], provenance)`
function; nothing mutates the input parse.

| Transform | Behavior |
|---|---|
| sport / sub_sport | Applied to **every** message the profile declares `sport`/`sub_sport` on (sport, session, lap, workout), so a file can never end up internally contradictory. Names or raw numbers accepted. |
| device identity | `file_id` + the **creator** `device_info` entry (`device_index == 0`) only — a heart-rate strap did not create the file. `product` must be numeric (products are vendor-specific). |
| time shift | Every field the merged profile types `date_time` or `local_date_time`, from the profile itself (no hand-list to rot). Relative spacing and the local/UTC offset are preserved by construction. |

Output is re-encoded through F12 and re-parsed in `strict` mode
(`output_strict_ok`), exactly like `repair`.

## The three critique-mandated changes, as built
1. **Encoder defect fixed first** — shipped separately as 0.4.2 (see below).
2. **PRD amended** — the sport non-goal now distinguishes inference
   (forbidden) from user-directed edits (explicit + provenanced); the stale
   analytics non-goal superseded by M2.7 was corrected in the same pass.
3. **No sub-sport inference** — the spec's "set to `generic` automatically"
   was cut. `sub_sport` changes only when named; when sport changes and a
   non-generic sub-sport is left in place, chiptime emits
   `SPORT_PAIR_IMPLAUSIBLE` and changes nothing. Flag, don't fix.

## Two findings the critique surfaced (both real, both fixed)

**1. A shipped bug in `repair`** (released as 0.4.2). Files whose field 253
was declared `byte[4]` and reassembled during decode could not be repaired at
all — `EncodeError: 1149238800 bytes exceeds size 4`. The encoder replayed
the source encoder's mistake instead of emitting canonical wire form. Found
by running an identity round-trip (`parse → encode → parse`) across the whole
corpus during critique rather than assuming the encoder was lossless.

**2. A taxonomy coverage gap.** Item #24 (unknown enum values pass through
with raw values) had **no corpus case** — a contract #7 violation hiding in
plain sight. Added `protocol/unknown-enum-values`: unknown manufacturer
(64999), product (9999), sport (250), and sub_sport (240) all survive as raw
numbers. It doubles as F26's preservation fixture.

## Guards
- **Time-shift bounds**: every shifted value must land in
  `[0, 0xFFFFFFFE]`. `0xFFFFFFFF` is the invalid sentinel, so shifting *onto*
  it would silently null a real timestamp (contract #4). Out of range raises
  `TIME_SHIFT_OUT_OF_RANGE` and writes no bytes — never clamps.
- **Unknown fields are never shifted**: chiptime cannot know an unrecognized
  field is a timestamp, and guessing would corrupt data (contracts #6/#8).
- **No-op protection**: `edit()` with no edit raises `NO_EDIT_REQUESTED`
  (CLI exit 64) rather than silently copying a file.

## Verification
- 12 tests in `python/tests/test_edit.py`, including the acceptance
  criterion in its strong form: parse the input, parse the output, and assert
  the **set of changed fields is exactly the edited ones** — collateral change
  is a test failure, not an eyeball check.
- Round-trip, strict self-check, and platform-validation parity asserted.
- Determinism: identical inputs produce byte-identical output.
- Full gate green: ruff, format, mypy --strict, corpus (72 cases), 91 tests.

## Deviations from spec
- **Corpus cases**: the spec planned four new `edit/*` cases. Built one
  (`protocol/unknown-enum-values`, which closed a genuine taxonomy gap) and
  reused existing committed cases as edit fixtures — `multisport/triathlon`
  (sport across many messages), `clean/ride-smooth` (device),
  `temporal/zwift-local-timestamp-1989` (local/UTC pair),
  `devfields/stryd-known-vendor` (developer-field survival). Duplicating
  existing inputs under an `edit/` prefix would have added corpus weight
  without adding coverage; the corpus pins *parse* behavior, and edit
  behavior is asserted against those pinned inputs.
- **`--validate` CLI flag**: deferred at critique (BACKLOG) — `chiptime
  validate` composes.
