# Feature: F36 — The semantic model for TypeScript

> Status: CRITIQUED

## Purpose

Fill the `activity` block, and with it close the parity gap: **all 72 corpus cases byte-identical
to their committed `expected.json`**.

Ports `model.py` and the five `semantics/` modules (~1,490 lines): the canonical
Activity → Sessions → Laps → Records model with columnar streams, the timer state machine, gap
classification, declared-vs-derived reconciliation, sensor and swim and lap sanity checks, and the
GPS plausibility gate.

This is the last feature before the CLI, and the last one whose output the corpus can measure.

## Context Check
- [x] `docs/PRD.md` — §6.1 (semantics is order-independent by construction; two-pass), §7.2 (the
      model), §7.5 (the canonical shape), contract #4 (zero ≠ null), #8 (honest non-recovery), #9
      (message order is untrusted)
- [x] `docs/INDEX.md` — mirrors F7 (semantic model), F8 (timers/gaps), F9 (reconcile/rebuild),
      F10 (GPS plausibility), F15 (tier-2 depth), F17, F21
- [x] `docs/architecture/OVERVIEW.md` — `semantics.build` imports decode/model/message/errors and
      the four sibling modules; nothing imports `semantics` except `api`
- [x] `docs/dependencies/DEPENDENCY_MAP.md` — F35 supplies `parse()`; runtime deps stay zero
- [x] `docs/edge-case-taxonomy.md` — items below
- [x] No duplication: the CLI is F37; analytics is F39 and is never imported by the core

## Taxonomy Coverage

**No new corpus cases** — fifth feature running. The 61 activity cases already carry every
expectation; this feature is what makes TypeScript reproduce them.

| Taxonomy item # | Summary | Corpus case(s) |
|---|---|---|
| 28 | `enhanced_` field pairs: prefer enhanced, reconcile, never emit both silently | `clean/ride-smooth`, `sensors/enhanced-*` |
| 34 | Sentinel tails trimmed from arrays | `protocol/array-fields` |
| 41 | Non-monotonic timestamps — explicit policy, recorded | `temporal/*` |
| 47 | Timezone/DST: the UTC stream is immune by construction | `temporal/local-offset` |
| 50 | Summary-first and summary-last layouts both legal — two-pass assembly | `semantics/*` |
| 62 | HR/power spike and flatline flags | `sensors/*` |
| 64 | Zero is real, null is absent, through every derived total | all activity cases |
| 72 | Swim: lengths, strokes, SWOLF inputs | `swim/*` |
| 92 | Declared vs derived totals, field by field, with discrepancies | `reconcile/summary-mismatch` |
| 93, 97, 98 | avg > max, zero-duration sessions, implausible units | `reconcile/*`, `sensors/*` |
| 94 | Lap coverage defects | `reconcile/*` |
| 95, 96 | Missing session / activity message → rebuild, marked `rebuilt` | `reconcile/no-session-rebuild` |
| 10 (GPS) | Bounce-spike gate, Null Island, virtual-GPS exemption | `gps/*` |

## Requirements

### 1. `js/src/model.ts`
1. `Stream`, `Records`, `Totals`, `Lap`, `Length`, `Gap`, `Discrepancy`, `Session`, `DeviceInfo`,
   `AthleteProfile`, `Event`, `Activity` mirroring `model.py`.
2. **Times are stored as FIT seconds (numbers), not `Date`.** Every timestamp in the canonical
   activity block goes through `strftime("%Y-%m-%dT%H:%M:%SZ")` in Python, so the integer
   formatter from F34 produces it exactly, and `Date` — banned in `js/src` since F34 — is never
   needed. This is a deliberate structural difference from the Python model, recorded because a
   reader diffing the two will notice it.
3. Streams are columnar: `values: (number | null)[]` with `null` for absent. Zero is a real zero
   (contract #4), and nothing in this layer may blur that.
4. `Records.rows()` as the row-oriented convenience view; `to_pandas` has no TypeScript analogue
   and is deliberately absent.

### 2. `js/src/semantics/build.ts`
5. `buildActivity(messages, warnings, provenance, scope, { skippedRanges, forensic })` mirroring
   `build_activity` — the two-pass, order-independent assembly (contract #9, taxonomy #50).
6. Session shells from `session` messages; rebuild from records when absent, marked `rebuilt`
   (taxonomy #95). Activity-message synthesis (#96).
7. Record assignment to sessions by time ownership; stream construction; `enhanced_` pair merging
   with disagreement reporting (#28); relative-elapsed derivation; time-sanity flags.
8. Local-offset handling (#47) and HRV interval collection.

### 3. `js/src/semantics/{timers,gaps,reconcile,plausibility}.ts`
9. `buildTimerState` — the timer machine and the three durations (ADR-0005); `movingSeconds`.
10. `classifyGaps` — smart recording / auto-pause / manual stop / post-timer / corruption /
    unknown, each with the human `evidence` sentence (ADR-0005 §7).
11. `reconcile`, `deriveAscentDescent`, `sensorFlags`, `swimChecks`, `lapChecks` — declared vs
    derived, field by field.
12. `gatePositions` — the GPS bounce-spike gate, Null Island, virtual exemption.

### 4. Numeric hazards specific to this layer
13. **`pyRoundN` at `plausibility.py:111`** (`round(max(...), 1)`), which lands in a provenance
    detail string. `Math.round` is banned; the two-argument form needs the kernel.
14. **Accumulation order is part of the contract.** Derived totals sum over records; a different
    iteration order changes the last bits of a float sum. Every accumulation walks the same
    sequence Python's does.
15. **The haversine is ADR-0009 §6's named hazard, and this is where it finally executes.**
    `sin`/`cos`/`asin` are not bit-identical between libm and V8. The ADR's position is that
    thresholding and rounding absorb the difference and the corpus gates it; F36 is the first
    feature that tests that claim rather than asserting it. If a `gps/*` case diverges, the fix is
    to widen the rounding at the site — **not** to regenerate the snapshot (ADR-0009 §1).

### 5. The gate
16. `check_parse_parity.py` **loses its two tiers**: every one of the 72 cases is compared against
    its committed `expected.json`, byte for byte, in lenient mode, with strict and forensic
    compared implementation-to-implementation.
17. Double-parse determinism, as the Python conformance runner does it.
18. The tier-2 whitelist and its explanatory comment are deleted, not left behind — a scaffold that
    outlives its reason becomes a place where coverage quietly hides.

## Acceptance Criteria
- [ ] **All 72 corpus cases byte-identical to their committed `expected.json`** in lenient mode
- [ ] Strict and forensic agree between implementations for all 72
- [ ] Double-parse produces identical bytes
- [ ] The `gps/*` cases pass with the haversine as ported — or the divergence is characterized and
      fixed at the rounding site, with the finding written down either way
- [ ] `Date` still absent from `js/src` (the guard stays green)
- [ ] Zero survives as zero and `null` as absent through every derived total
- [ ] Rebuilt sessions are marked `rebuilt: true` and carry provenance
- [ ] `tsc`, Biome, guards, vitest, determinism, pack smoke, all parity gates green
- [ ] Per-mode behavior: `forensic` detects like lenient but never drops values — compared
      explicitly, since this is the layer where the two most differ

## Public API Impact

**New TypeScript exports**: the model types and `Activity` at `chiptime/model`;
`ParseResult.activity` becomes populated. `buildActivity` at `chiptime/semantics`.
Nothing published yet — the CLI (F37) carries `npm 0.1.0`.

No Python change. No canonical JSON schema change: this fills a block schema 1 already defines.

## Architectural Placement

**`semantics` layer.** `semantics/*` imports `decode` (epoch constants), `model`, `message`,
`errors`. `decode` must never import `semantics` — the rule has been trivially true until now
because semantics did not exist, and this is the feature where it becomes a real constraint.

## Proposed Approach

Gate-first, as at F33/F34/F35, with one difference: the gate already exists and already knows the
answer. Wiring `buildActivity` into `parse()` turns 61 tier-2 cases into 61 tier-1 cases, and the
failure list *is* the work plan.

Port order follows the dependency chain — `model`, then `timers`/`gaps`/`reconcile`/`plausibility`
as leaves, then `build` which orchestrates them.

## Critique & Assessment

_Assessed 2026-08-21. The spec asked whether the haversine claim should be tested before the port
rather than discovered during it. It should, it was, and the answer changes what this feature has
to worry about._

### Finding 1 — ADR-0009 §6's central assumption, finally measured

Since F31 the ADR has carried a hedge: transcendental math (`sin`/`cos`/`asin`) is not bit-identical
between libm and V8, the difference is absorbed by thresholding and rounding, and the corpus gates
it. That was reasoning, not evidence, and F36 is the first feature that executes the code.

Measured **before** writing any of it, over the 54 real position pairs the `gps/*` corpus cases
actually contain, run through the identical haversine formulation in both runtimes:

| | |
|---|---|
| Bit-identical results | **53 of 54** |
| Largest absolute difference | **5.7 × 10⁻¹⁴ m** |
| Largest relative difference | **1.67 × 10⁻¹⁶** (one ULP) |

Fifty-seven femtometres, on a value that is thresholded against speeds in m/s and then rounded to
one decimal place. For that to change an outcome, a velocity would have to sit within ~10⁻¹⁵ of a
gate threshold or a `.05` rounding boundary.

The ADR's position is upheld, and it should now say this **in numbers** rather than in prose — a
future reader deciding whether to build the fixed-point math kernel held in BACKLOG deserves the
measurement, not the argument. Amendment E1: update ADR-0009 §6 with the figures and the method,
and note that the check is cheap to repeat if the corpus gains GPS cases.

This also reframes the feature's risk. The haversine was the spec's headline hazard; it is now the
best-characterized thing in it. The real risks are ordinary and larger: 1,490 lines of assembly
logic where float accumulation order, sort stability and null-vs-zero all reach canonical output.

### Finding 2 — one feature, because there is no partial gate

At ~1,490 lines this is near the 1,600 that got F33 split, and the instinct to split is right in
general. It fails here for the same reason it failed at F34: **the activity block is all or
nothing.** `buildActivity` produces sessions, laps, records and streams together; timers, gaps,
reconciliation and plausibility all feed the same object. A "model and streams first, checks
second" split leaves stage one with an activity block that no corpus case matches — a feature with
no gate, which is not a feature.

What makes the size tolerable is that the gate already exists and already knows every answer.
Wiring `buildActivity` into `parse()` converts 61 tier-2 cases into 61 tier-1 cases, and **the
failure list is the work plan**. That is a materially different position from F33, which had to
build its gate first.

### Finding 3 — the tier-2 scaffold must be deleted, not left inert

Requirement 18 already says so, and it is worth keeping as a requirement rather than a cleanup
note. The whitelist exists because the semantic layer did not; once it does, a whitelist left
behind is a place where coverage can quietly narrow again — and it would still pass. Removing it
is part of the feature, not tidying after it.

### Alternatives considered
1. *Split model+build from the four check modules.* Rejected above: no gate for stage one.
2. *Port the checks as no-ops first, then fill them.* Same defect in a different shape — every case
   fails until the last module lands, so the "gate-first" benefit is illusory and the failure list
   is noise rather than a plan.
3. *Build the fixed-point math kernel now.* Rejected on the measurement: one ULP on a value rounded
   to 0.1 does not justify a hard-to-audit module. Stays in BACKLOG with its trigger unchanged.

### At scale
Streams are columnar and per-session; an ultra-length activity produces arrays of tens of
thousands. Nothing here is quadratic except the position gate, which is a single forward pass. No
performance gate at F36 (F20 set the precedent that perf is its own feature).

### Contract check
- **Silent loss** — the position gate *nulls* implausible coordinates, and session rebuild
  *synthesizes*. Both must emit provenance; both are gated by the 72-case comparison, so a missing
  entry fails rather than passes quietly.
- **Determinism** — the two live hazards are float accumulation order in the derived totals and
  sort stability in record assignment. JavaScript's sort has been stable since ES2019, and the
  accumulations must walk Python's sequence exactly (Requirement 14).
- **Sentinels & zero-vs-null** — this is the layer where blurring them would be easiest and least
  visible, since a `null` and a `0` both look plausible in a total. Contract #4 is gated by every
  activity case.
- **Modes** — `forensic` never drops values where `lenient` does; this is the layer where they
  differ most, and both are compared.
- **Errors** — no new failure paths; warnings and provenance codes come from the registries
  transcoded at F33.
- **Corpus** — no new cases; the 61 activity cases are the specification.

### Simplification — nothing cut
`Records.to_pandas` has no TypeScript analogue and is already absent, which is a genuine
subtraction rather than a deferral. Beyond that, every module feeds the byte comparison.

### Final decision: **APPROVE** — one feature, with amendment E1

The spec's headline risk turned out to be its best-understood element, measured at one ULP before a
line was written. What remains is a large but ordinary port, against a gate that already knows
every answer.

## Dependencies
- **Depends on:** F31–F35; F7–F10/F15/F17/F21 in Python as the reference; ADR-0005, ADR-0009
- **Depended on by:** F37 (the CLI's `--summary`), F38+ (repair reads the model), F39 (analytics)

## Related
- ADR: [0005](../architecture/adrs/0005-timestamp-policies.md), [0009](../architecture/adrs/0009-cross-language-parity.md)
- Plan: [../m3-typescript-plan.md](../m3-typescript-plan.md)
- Implementation: `../implementation/f36-js-semantics.md` (created by `/implement`)
