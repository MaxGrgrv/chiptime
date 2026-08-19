# Feature: [Feature Name]

> Status: DRAFT | CRITIQUED | APPROVED | IMPLEMENTING | DONE

## Purpose
_Why does this feature exist? What problem does it solve?_

## Context Check
- [ ] Reviewed docs/INDEX.md for existing features
- [ ] Reviewed docs/architecture/OVERVIEW.md for architectural fit
- [ ] Reviewed docs/dependencies/DEPENDENCY_MAP.md for conflicts
- [ ] Reviewed docs/PRD.md for scope and principles alignment
- [ ] Reviewed docs/edge-case-taxonomy.md for related edge cases
- [ ] No duplication with existing features

## Taxonomy Coverage
_Which items from docs/edge-case-taxonomy.md does this feature address? Every parser-facing feature must map to taxonomy items (or state "none — infrastructure only")._

| Taxonomy item # | Summary | Corpus case(s) planned |
|---|---|---|
| _e.g. 2_ | _Truncated mid-record_ | _corpus/cases/structural/truncated-mid-record/_ |

## Requirements
1. _Requirement 1_
2. _Requirement 2_

## Acceptance Criteria
- [ ] _Criterion 1_
- [ ] Every taxonomy item above has at least one corpus case with committed expected output
- [ ] Behavior specified per mode (strict / lenient / forensic) where they differ

## Public API Impact
_New or changed public surface: functions, classes, CLI flags, canonical JSON schema fields. "None" if internal only. Canonical schema changes require a schema version note._

## Architectural Placement
_Which layer does this live in: intake / decode / recovery / profile / semantics / output / cli / corpus tooling?_

## Proposed Approach
_High-level implementation plan._

## Critique & Assessment
_Filled in during the critique phase:_
- **Alternatives considered:** _..._
- **Risks identified:** _..._
- **Simplification opportunities:** _..._
- **Contract check (silent loss / determinism / provenance / sentinels):** _..._
- **Final decision:** _..._

## Dependencies
- **Depends on:** _features/modules this requires_
- **Depended on by:** _features/modules that require this_

## Related
- ADR: _link to any architecture decision records_
- Implementation: _link to docs/implementation/<name>.md_
