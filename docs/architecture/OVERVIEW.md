# chiptime — Architecture Overview

> Living document. Updated by /implement and /post-impl-review as the system is built. Until code exists, the proposed architecture lives in [../PRD.md](../PRD.md); this file records the as-built state.

Status: **M2.8 in progress (0.7.0)** — F26 `edit`, F27 `trim`, F28 `reveal`/`scrub` shipped; F29 `convert`, F30 `merge` queued.
Next: **M3 — the TypeScript twin on the shared corpus** ([plan](../m3-typescript-plan.md) · [ADR-0009](adrs/0009-cross-language-parity.md)); the `js/` tree mirrors `python/src/chiptime/` module-for-module, so every row in the table below gains a TypeScript twin at the same address.

## Layers (planned, from PRD — subject to shape agreement)

- **intake** — content sniffing, unwrapping (zip/gz), chained-file splitting, routing by file type
- **decode** — header parsing, record framing, definition messages, base types, CRC
- **recovery** — resynchronization, truncation salvage, frame-shift detection
- **profile** — global FIT profile tables, developer-field registry
- **semantics** — canonical model, timer state machine, gap classification, reconciliation, plausibility gates
- **output** — canonical JSON, provenance, warnings, error model
- **cli** — command-line surface

## Modules (as built)

| Module | Layer | Purpose |
|---|---|---|
| `chiptime._api` | api | `parse()` mode policy, chained-part loop, strip_pii/include_unknown; `iter_frames`/`iter_messages` |
| `chiptime.intake` | intake | Container unwrap (gzip/zip), content sniffing, NOT_FIT detection |
| `chiptime.frames` | decode | Crash-proof frame reader: headers, definitions (incl. dev specs), data, CRC, defects (ADR-0003) |
| `chiptime.decode` | decode | Frames → Messages: sentinels→null, scale/offset, enums, timestamps (incl. compressed), salvage |
| `chiptime.profile` | profile | Base types + hand-authored core tables, fitdecode-verified (ADR-0004) |
| `chiptime.profile.registry` | profile | Known-vendor developer-field promotion (Stryd/greenTEG/Moxy) |
| `chiptime.message` | decode | Message / FieldValue / DevFieldOrigin |
| `chiptime.model` | semantics | Activity/Session/Records/Stream canonical model (PRD §7) |
| `chiptime.semantics.build` | semantics | Order-independent model assembly, streams, enhanced pairs |
| `chiptime.semantics.timers` | semantics | Timer state machine, three durations (ADR-0005) |
| `chiptime.semantics.gaps` | semantics | Gap classification with evidence (ADR-0005 §7) |
| `chiptime.semantics.reconcile` | semantics | Declared-vs-derived discrepancies, sanity flags, ascent/descent |
| `chiptime.semantics.plausibility` | semantics | GPS bounce-spike gate, Null Island, virtual exemption |
| `chiptime.cli` | cli | parse/inspect/codes; agent exit-code contract |
| `chiptime.encode` | encode (M2) | Canonical FIT writer: lossless re-emit + profile synthesis (ADR-0006) |
| `chiptime.repair` | repair (M2) | Salvage → synthesize → valid .fit; honest refusal (#16) |
| `chiptime.metrics` | analytics (optional) | Mean-max curves, zone time, SWOLF — never imported by core |
| `chiptime.validate` | repair (M2) | Platform acceptance profiles (heuristic, #99/#102) |
| `chiptime.errors` | errors (leaf) | FitError hierarchy, Defect/Diagnostic/ProvenanceEntry, code registries |
| `chiptime.result` | output | ParseResult + canonical schema v1 shaping |
| `chiptime.canonical` | output | RFC 8785 canonical JSON serialization (ADR-0002); the determinism contract |
| `corpus/tools/*` | corpus tooling (outside package) | Deterministic fixture generation, independent of chiptime by design (ADR-0001) |

## TypeScript twin (`js/src`) — as built

Module-for-module with the table above, so a Python change has an obvious TypeScript address
([ADR-0009](adrs/0009-cross-language-parity.md), [M3 plan](../m3-typescript-plan.md)).

| Module | Layer | Purpose | Status |
|---|---|---|---|
| `canonical.ts` | output | RFC 8785 serializer; the number policy; UTF-8 encoder; the refusal set | F31 ✅ |
| `numeric.ts` | leaf (internal) | Python rounding semantics: `pyRound`, `pyRoundN`, `floorDiv`, `divmod` | F31 ✅ |
| `index.ts` | api | Public surface — the parsing verbs arrive at F34/F35 | F31 ✅ |
| `profile/*` | profile | Base types, merged message/enum tables (transcoded from Python), vendor registry | F32 ✅ |
| `frames.ts`, `decode.ts`, `message.ts` | decode | Crash-proof frame reader; frames → messages | F33 |
| `intake.ts`, `inflate.ts`, `api.ts`, `result.ts`, `cli.ts` | intake / api / output / cli | Unwrap, recover, shape, and the first CLI verbs | F34 |
| `model.ts`, `semantics/*` | semantics | The canonical model — full corpus parity | F35 |
| `encode.ts`, `repair.ts`, `validate.ts` | encode / repair | Writer, salvage, platform profiles | F36 |
| `metrics/*` | analytics (optional) | The optional layer; never imported by core | F37 |
| `edit.ts`, `trim.ts`, `privacy.ts` | write verbs | Metadata surgery, crop, privacy | F38–F40 |

Invariants specific to this tree, enforced rather than documented:

- **Zero runtime dependencies**, same as Python (`js/scripts/smoke.sh` asserts no `node:` import
  reaches `dist`, so the browser build cannot regress silently).
- **`Math.round` is banned** outside `numeric.ts` — it is half-up where Python is half-to-even
  (`js/scripts/guards.mjs`, verified to exit non-zero on a probe).
- **`Date` never appears on an output path**: `toISOString()` always emits milliseconds, which the
  Python formatter does not (ADR-0009 §5). `canonical.ts` refuses a `Date` outright.
- **The profile is transcoded, not re-derived** (ADR-0009 §8). Two CI gates: regenerate-and-diff
  for staleness, `check_profile_parity.py` for transcoding faults. Note what this means for the
  corpus — it proves the two implementations agree, not that either matches reality; the outward
  check is `check_profile_against_fitdecode.py`.

