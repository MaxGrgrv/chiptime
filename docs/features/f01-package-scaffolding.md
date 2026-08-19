# Feature: F1 — Python Package Scaffolding

> Status: DONE

## Purpose
Stand up the `python/` package so every subsequent feature lands in a tooled, testable, zero-runtime-dependency project. Infrastructure only.

## Context Check
- [x] Reviewed docs/INDEX.md for existing features
- [x] Reviewed docs/architecture/OVERVIEW.md for architectural fit
- [x] Reviewed docs/dependencies/DEPENDENCY_MAP.md for conflicts
- [x] Reviewed docs/PRD.md for scope and principles alignment
- [x] Reviewed docs/edge-case-taxonomy.md for related edge cases
- [x] No duplication with existing features

## Taxonomy Coverage
None — infrastructure only.

## Requirements
1. `python/` uv-managed project, `src/chiptime/` layout, `py.typed`, Python ≥ 3.11 (pinned 3.13 locally).
2. Zero runtime dependencies; dev group: pytest, hypothesis, mypy (strict), ruff. Separate `baselines` group (fitparse, fitdecode) for the M2 scoreboard — never default-installed.
3. `chiptime` console script entry point (stub until F11).
4. All three tools green on the empty package.

## Acceptance Criteria
- [x] `uv run python -c "import chiptime"` works
- [x] `uv run ruff check` / `uv run mypy` / `uv run pytest` all pass
- [x] uv.lock committed

## Public API Impact
`chiptime.__version__ = "0.1.0.dev0"`. Nothing else yet.

## Architectural Placement
Repo infrastructure (monorepo `python/` leg per PRD §12).

## Proposed Approach
Hand-written pyproject (hatchling) rather than `uv init` for exact control; LICENSE copied into `python/` for sdist correctness.

## Critique & Assessment
- **Alternatives considered:** Poetry / plain pip-tools (rejected: uv is the agreed convention, fastest, lockfile-native); flat layout (rejected: src layout prevents accidental cwd imports — matters for a parser tested against corpus paths).
- **Risks identified:** dev-tool version drift → pinned floors in dependency-groups, lockfile committed. Baselines group leaking into runtime deps → kept as a non-default group.
- **Simplification opportunities:** none meaningful; this is already minimal.
- **Contract check:** N/A (no parser code).
- **Final decision:** APPROVE

## Dependencies
- **Depends on:** —
- **Depended on by:** every subsequent feature

## Related
- Implementation: [../implementation/f01-package-scaffolding.md](../implementation/f01-package-scaffolding.md)
