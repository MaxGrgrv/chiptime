# Implementation: F1 — Python Package Scaffolding

> Feature Spec: [../features/f01-package-scaffolding.md](../features/f01-package-scaffolding.md)

## Summary
uv-managed `python/` project: hatchling build, src layout, `py.typed`, zero runtime deps, dev tooling (pytest/hypothesis/mypy-strict/ruff) green, `baselines` dependency group isolated for M2 scoreboard use.

## Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| python/pyproject.toml | Added | Build, metadata, tool config; `dependencies = []` documented as a contract |
| python/src/chiptime/__init__.py | Added | Package root, `__version__ = "0.1.0.dev0"` |
| python/src/chiptime/py.typed | Added | PEP 561 marker |
| python/tests/test_version.py | Added | Smoke test |
| python/README.md, python/LICENSE, python/.python-version | Added | sdist correctness + interpreter pin (3.13) |
| python/uv.lock | Added | Locked dev environment |

## Corpus Cases Added
None — infrastructure.

## Key Implementation Decisions
1. Interpreter pinned to 3.13 locally while `requires-python = ">=3.11"` — newest stable for dev, floor per PRD §12.
2. `chiptime = "chiptime.cli:main"` script declared now so the entry point never needs a packaging change (cli lands in F11; until then the module simply doesn't exist — not importable, not shipped as broken).

## Deviations from Spec
- None.

## Lessons Learned
uv resolved and synced in seconds; lockfile committed from day one avoids the fitparse-era "works on my machine" drift.

## Post-Implementation Checklist
- [x] Feature spec status updated to DONE
- [x] INDEX.md updated
- [x] DEPENDENCY_MAP.md updated
- [x] Architecture docs updated (no change needed)
- [x] All new behavior covered (smoke test)
- [x] Provenance N/A (no parser code)
- [x] Determinism N/A
- [x] Skills assessed — no updates needed
