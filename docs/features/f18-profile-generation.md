# Feature: F18 — Full Profile Generation (M2.5)

> Status: DONE

## Purpose
Close the semantic-breadth gap the soak exposed (workouts 66–71% unknown, monitoring 95%, settings/weight 33%): generate the full message/field/enum tables from the maintainer's locally-downloaded FIT SDK, committing only our generated output (ADR-0004 — the SDK zip and Profile.xlsx never enter the repo).

## Taxonomy Coverage
Breadth enabler for #77 (strength), #80–82 (workout/course/monitoring/niche modes), #24 (enum coverage). Existing corpus cases with real message types re-snapshot with named semantics.

## Requirements
1. `scripts/generate_profile.py <sdk-zip-or-xlsx>`: stdlib-only xlsx reader (zip + XML — no new dependencies, even dev); parses Types (enums + `mesg_num`) and Messages sheets; skips subfield rows (dynamic resolution stays curated, F15) and component multi-scales (raw preserved).
2. Output `python/src/chiptime/profile/generated.py`: deterministic (sorted), provenance header (SDK version from filename, regeneration command), our `FieldDef`/`MessageDef` shapes, `semicircles → degrees` rule applied globally (core's documented divergence).
3. Merge in `profile/__init__`: field-level — generated breadth + hand-authored core overriding per-field (core is fitdecode-verified and curated); enums merge with generated superset winning per value.
4. Gate extended: `check_profile_against_fitdecode` verifies the MERGED tables against fitdecode's full profile over their intersection (version skew 21.158 vs 21.171 reported, not failed).
5. Soak re-run must show unknown% collapse on workouts/monitoring/settings.

## Acceptance Criteria
- [x] Generated tables committed; SDK files absent from repo and .gitignore'd defensively
- [x] Cross-check gate green over the intersection
- [x] Soak: high-unknown file count drops materially; corpus re-snapshotted deliberately

## Critique & Assessment
- **Alternatives considered:** openpyxl dev-dep (rejected: stdlib zip+XML is ~60 lines and keeps even the dev tree lean); generated-wins merge (rejected: core is verified + carries curated units; field-level core-override keeps both).
- **Risks identified:** xlsx quirks (hex values, comma scales) → handled explicitly; version skew vs fitdecode → intersection-only comparison with counts reported.
- **Contract check:** unknown-tolerance unchanged (a stale profile still never crashes); licensing rule enforced (generator reads outside the repo; output carries non-affiliation note).
- **Final decision:** APPROVE

## Dependencies
- **Depends on:** F3 (ADR-0004) · **Depended on by:** F19 (real-file semantics), F21

## Related
- ADR: [0004](../architecture/adrs/0004-profile-strategy.md)
- Implementation: [../implementation/f18-profile-generation.md](../implementation/f18-profile-generation.md)
