# Feature: F19 — Real-File Corpus Promotion + PII Policy (M2.5)

> Status: DONE

## Purpose
Pin real-world behavior as conformance, under ADR-0007's privacy/licensing rules: a git-ignored private tier holding the maintainer's own files, sha-guarded and snapshot-tested exactly like public cases. Plus: resolve the 10 remaining cycling DISTANCE_FROZEN warnings (suspected Wahoo quirk, #84).

## Taxonomy Coverage
| # | Summary | Case (tier) |
|---|---|---|
| 84 ★ | Wahoo ELEMNT ROAM field-population quirks | private: roam ride + finding below |
| 75 ★ | Real multisport race | private: IRONMAN 5-session file |
| 73/56 ★ | Real pool + OW swims | private: swim files |
| 10/19 ★ | Real resync-surviving damage | private: filtered.fit (9 resyncs) |
| 2 ★ | Real in-progress/crash file | private: inProgressActivity.fit |

## Requirements
1. `corpus/private/` git-ignored; runner discovers `corpus/private/MANIFEST.json` when present; `gen_all` handles `"build": "external"` (sha-verify + `--expected` only, never regenerate).
2. `corpus/tools/promote_real.py <file> <category/slug> [--note]`: copies, hashes, snapshots, updates the private manifest.
3. Promote 6 files: filtered, one pool swim, ROAM ride, IRONMAN multisport, inProgressActivity, one Garmin-format activity.
4. Investigate cycling DISTANCE_FROZEN on real rides; tune or reclassify with evidence.
5. Nothing public gains real bytes in F19 (ADR-0007 §3).

## Acceptance Criteria
- [x] Private cases parametrize locally, skip cleanly when absent; public CI unaffected
- [x] git status shows no real bytes staged; .gitignore guards the tier
- [x] DISTANCE_FROZEN investigation concluded with a code or docs change

## Critique & Assessment
- **Alternatives considered:** coordinate-fuzzing for public promotion now (rejected: fuzzing GPS while keeping streams consistent — distance/speed derive from positions — is its own project; deferred to pre-public review); committing encrypted blobs (rejected: keys-in-repo theater).
- **Risks identified:** private-tier drift (cases only on one machine) → manifest + sha recorded; promotion tool makes re-promotion deterministic.
- **Contract check:** determinism per-machine preserved (runner parametrizes on what exists); honest tiering documented for future contributors.
- **Final decision:** APPROVE

## Related
- ADR: [0007](../architecture/adrs/0007-real-file-pii-policy.md)
- Implementation: [../implementation/f19-real-file-corpus.md](../implementation/f19-real-file-corpus.md)
