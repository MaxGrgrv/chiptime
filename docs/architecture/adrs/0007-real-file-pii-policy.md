# ADR-0007: Real-file corpus — privacy policy and licensing boundary

> Status: ACCEPTED · 2026-08-18 · Feature: F19

## Context
Real device files are the credibility backbone (the soak proved the synthetic
corpus predicts reality, but conformance must eventually pin real bytes). Real
files carry PII — start/end coordinates are a home address (taxonomy #103),
serials identify devices — and the repo is destined to go public. Separately,
the maintainer's Downloads folder contains official Garmin SDK sample files
(MonitoringFile.fit, Workout*.fit, HrmPluginTest*.fit, Settings.fit,
WeightScaleSingleUser.fit): those are FIT-Protocol-licensed and are BANNED
from the repo permanently (CLAUDE.md licensing rule; the one thing even
SDK-vendoring projects flag as Garmin-licensed).

## Decision
1. **Two corpus tiers.** `corpus/cases/**` stays public-safe (synthetic +
   explicitly cleared files). New: `corpus/private/**` — git-ignored,
   machine-local, same triplet format, separate git-ignored manifest. The
   conformance runner loads both manifests; absent private cases simply don't
   parametrize (public CI unaffected, maintainer machines get full coverage).
2. **Promotion tool, not hand-copying**: `corpus/tools/promote_real.py`
   copies a file into the private tier, writes `case.json` with
   `"source": "own-archive"` and `"build": "external"` (gen_all sha-verifies
   external inputs instead of regenerating), and snapshots expected.json.
3. **Public promotion is opt-in per file** and requires BOTH: maintainer
   consent recorded in case notes AND a PII pass — `strip_pii` derivative or
   documented "public event" rationale for coordinates (a race start line is
   public; a Tuesday training loop from home is not). None promoted publicly
   in F19 — decision deferred to the pre-public-flip review.
4. **SDK sample files: never in either tier.** The soak harness may read them
   from Downloads; nothing under `corpus/` may.

## Consequences
- Public repo keeps its everything-reproducible property (every public input
  regenerates from committed generators).
- Real-file conformance exists where it matters (maintainer + future trusted
  CI) without leaking a single coordinate.
- The "donate your broken file" page (M4 flywheel) will need a consent flow
  that feeds tier decisions — designed then.
