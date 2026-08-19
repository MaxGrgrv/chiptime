# chiptime — Architecture Overview

> Living document. Updated by /implement and /post-impl-review as the system is built. Until code exists, the proposed architecture lives in [../PRD.md](../PRD.md); this file records the as-built state.

Status: **M2.5 shipped (0.3.0).** Next: M3 (TypeScript twin on the shared corpus).

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
