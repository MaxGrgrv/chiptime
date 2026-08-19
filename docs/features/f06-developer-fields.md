# Feature: F6 — Developer Fields

> Status: DONE

## Purpose
Full taxonomy #22 — the #1 real-world parser killer. Resolve developer fields via `developer_data_id`/`field_description`, salvage every malformed variant (missing metadata, null names, late descriptions, reused indices), and tag known vendors for stream promotion.

## Context Check
- [x] All five context docs reviewed. F3 left dev fields as raw `dev_{idx}_{num}` placeholders.

## Taxonomy Coverage

| Taxonomy item # | Summary | Corpus case(s) |
|---|---|---|
| 22a | Metadata messages missing while dev fields referenced | devfields/missing-field-description, devfields/no-developer-data-id |
| 22b | Null/absent field name (RunScribe, fitparse #62) | devfields/null-field-name |
| 22c | Same dev index reused by different apps | devfields/dev-index-reused |
| 22d | Known-vendor mapping (Stryd / CORE-greenTEG / Moxy) | devfields/stryd-known-vendor |
| 22 (late) | field_description arriving after its data (fit-file-parser #54 class) | devfields/late-field-description |

## Requirements
1. Decoder tracks `developer_data_id` (index → application_id, manufacturer) and `field_description` ((index, field#) → name/type/scale/offset/units/native refs).
2. Resolution per dev field: description present → decode per its base type, apply its scale/offset, sanitized name (collision-suffixed); description absent or name null → synthesized `dev_{idx}_{num}`, raw bytes kept, one warning per (idx,num).
3. **Late descriptions back-fill**: at `finish()`, earlier messages with then-unresolved dev fields are re-resolved if the description arrived later — with provenance (`DEV_FIELD_RESOLVED_LATE`).
4. Index reuse: later `developer_data_id`/`field_description` for the same index overwrite forward (correct wire semantics), one `DEV_INDEX_REDEFINED` warning.
5. Vendor registry (`profile/registry.py`): vendor = manufacturer enum name from developer_data_id; `(vendor, field-name)` → canonical stream name + units, seeded with Stryd power/LSS, greenTEG core temp, Moxy SmO2/THb. Carried on `DevFieldOrigin.canonical_name` for F7 stream promotion.
6. `DevFieldOrigin` serialized in canonical JSON (application_id hex, vendor, canonical name).

## Acceptance Criteria
- [x] 6 corpus cases green in all modes; fitparse #62/#124 scenarios decode without crash, data preserved
- [x] Clean seeds unaffected (no dev machinery leakage)

## Public API Impact
`DevFieldOrigin` gains `canonical_name`; canonical JSON `developer` object gains it too (pre-release schema evolution, snapshots regenerated).

## Architectural Placement
decode layer + profile/registry (data-only).

## Proposed Approach
Per requirements; back-fill implemented as message rebuild in `Decoder.finish()` (frozen dataclasses → `dataclasses.replace`).

## Critique & Assessment
- **Alternatives considered:** two-pass decode (pre-scan all descriptions first) — rejected: breaks streaming `iter_messages` semantics; back-fill at finish gives batch users the same result without penalizing streaming. Name-keyed registry per application_id UUID — rejected: UUIDs vary per app build; manufacturer_id is stable and already in our enum.
- **Risks identified:** name collisions between dev and native fields → deterministic `_{idx}_{num}` suffix policy; description scale=0 division → treated as "no scaling" (matches SDK semantics).
- **Simplification opportunities:** none taken; every branch maps to a documented wild failure.
- **Contract check:** nothing dropped (raw kept when undecodable); synthesized names + back-fills all carry warnings/provenance; determinism — resolution depends only on file order.
- **Final decision:** APPROVE

## Dependencies
- **Depends on:** F3
- **Depended on by:** F7 (dev stream promotion), M4 registry growth

## Related
- Implementation: [../implementation/f06-developer-fields.md](../implementation/f06-developer-fields.md)
