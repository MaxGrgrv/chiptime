---
description: Migration guides — moving to chiptime from other Python FIT parsing libraries with line-by-line API mappings.
---

# Migrate to chiptime

Line-by-line API mappings for moving existing code to chiptime. The guides
focus on mechanics: how each concept maps, what you can delete after
switching, and where behavior differs so nothing surprises you.

- [Migrate from fitparse](from-fitparse.md)
- [Migrate from fitdecode](from-fitdecode.md)

Two behavior notes that apply to any migration:

1. **Damaged files parse instead of raising** (in the default `lenient`
   mode). Code structured around exception handling moves to checking
   `result.ok`, `result.errors`, and `provenance[]` — and `strict` mode
   restores raise-on-first-violation semantics where you want them.
2. **`None` is trustworthy.** FIT sentinel values are converted to `None`
   during decode, and zero is preserved as a real measurement, so hand-rolled
   sentinel guards can be deleted.
