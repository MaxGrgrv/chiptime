# chiptime — Documentation Index

Master index of all documentation. Updated with every feature change.

## Core Documents

| Doc | Purpose |
|---|---|
| [PRD.md](PRD.md) | Product requirements — vision, principles, scope, architecture, roadmap |
| [edge-case-taxonomy.md](edge-case-taxonomy.md) | The 104-item FIT edge-case taxonomy — the parser-behavior backlog |
| [BACKLOG.md](BACKLOG.md) | Items deferred during critique cycles |
| [for-agents.md](for-agents.md) | Generated agent-facing reference: codes, exit codes, schema (do not hand-edit) |
| [../CHANGELOG.md](../CHANGELOG.md) | Release notes |
| [../website/](../website/) | Public docs site (Material for MkDocs; `mkdocs.yml` at root; deploys to GitHub Pages via the docs workflow, manual trigger until the repo is public) |
| [architecture/OVERVIEW.md](architecture/OVERVIEW.md) | Living as-built architecture document |
| [dependencies/DEPENDENCY_MAP.md](dependencies/DEPENDENCY_MAP.md) | Cross-feature and module dependency tracking |

## Research

| Doc | Purpose |
|---|---|
| [research/licensing-conformance-naming.md](research/licensing-conformance-naming.md) | FIT SDK license analysis, cross-language conformance-suite patterns, name availability |
| [research/sport-metrics-domain.md](research/sport-metrics-domain.md) | Per-sport metrics/pacing/interval conventions + verified naming-safety list — M2.7 foundation |

## Features

| Feature | Status | Spec | Implementation |
|---|---|---|---|
| F1 Package scaffolding | DONE | [spec](features/f01-package-scaffolding.md) | [impl](implementation/f01-package-scaffolding.md) |
| F2 Corpus infra + canonical serializer | DONE | [spec](features/f02-corpus-and-canonical.md) | [impl](implementation/f02-corpus-and-canonical.md) |
| F3 Decode core | DONE | [spec](features/f03-decode-core.md) | [impl](implementation/f03-decode-core.md) |
| F4 Intake (sniff/unwrap/chain/route) | DONE | [spec](features/f04-intake.md) | [impl](implementation/f04-intake.md) |
| F5 Recovery (resync + salvage) | DONE | [spec](features/f05-recovery-resync.md) | [impl](implementation/f05-recovery-resync.md) |
| F6 Developer fields | DONE | [spec](features/f06-developer-fields.md) | [impl](implementation/f06-developer-fields.md) |
| F7 Semantic model (streams) | DONE | [spec](features/f07-semantic-model.md) | [impl](implementation/f07-semantic-model.md) |
| F8 Timers, gaps, timestamp policies | DONE | [spec](features/f08-timers-gaps-timestamps.md) | [impl](implementation/f08-timers-gaps-timestamps.md) |
| F9 Reconciliation, rebuild, multisport | DONE | [spec](features/f09-reconcile-rebuild-multisport.md) | [impl](implementation/f09-reconcile-rebuild-multisport.md) |
| F10 GPS plausibility | DONE | [spec](features/f10-gps-plausibility.md) | [impl](implementation/f10-gps-plausibility.md) |
| F11 CLI, agent docs, M1 wrap (0.1.0) | DONE | [spec](features/f11-cli-agent-docs-m1-wrap.md) | [impl](implementation/f11-cli-agent-docs-m1-wrap.md) |
| F12 FIT encoder | DONE | [spec](features/f12-encoder.md) | [impl](implementation/f12-encoder.md) |
| F13 Repair pipeline | DONE | [spec](features/f13-repair-pipeline.md) | [impl](implementation/f13-repair-pipeline.md) |
| F14 Platform validation profiles | DONE | [spec](features/f14-validation-profiles.md) | [impl](implementation/f14-validation-profiles.md) |
| F15 CRC triage + Tier-2 depth | DONE | [spec](features/f15-crc-triage-tier2-depth.md) | [impl](implementation/f15-crc-triage-tier2-depth.md) |
| F16 Robustness gate + M2 wrap (0.2.0) | DONE | [spec](features/f16-scoreboard-m2-wrap.md) | [impl](implementation/f16-scoreboard-m2-wrap.md) |
| F17 Soak-sprint fixes (M2.5) | DONE | [spec](features/f17-soak-fixes.md) | [impl](implementation/f17-soak-fixes.md) |
| F18 Full profile generation (M2.5) | DONE | [spec](features/f18-profile-generation.md) | [impl](implementation/f18-profile-generation.md) |
| F19 Real-file corpus + PII policy (M2.5) | DONE | [spec](features/f19-real-file-corpus.md) | [impl](implementation/f19-real-file-corpus.md) |
| F20 Performance pass (M2.5) | DONE | [spec](features/f20-performance-pass.md) | [impl](implementation/f20-performance-pass.md) |
| F21 HRV + analytics foundation (M2.5) | DONE | [spec](features/f21-swim-hrv-metrics.md) | [impl](implementation/f21-swim-hrv-metrics.md) |
| F22 Ecosystem-issue hardening (M2.6) | DONE | [spec](features/f22-issue-mining-hardening.md) | [impl](implementation/f22-issue-mining-hardening.md) |
| F23 Sport profiles + pacing (M2.7) | DONE | [spec](features/f23-sport-profiles-pacing.md) | [impl](implementation/f23-sport-profiles-pacing.md) |
| F24 Interval & structure detection (M2.7) | DONE | [spec](features/f24-interval-structure.md) | [impl](implementation/f24-interval-structure.md) |
| F25 Insights, load, analyze CLI (M2.7) | DONE | [spec](features/f25-insights-load-analyze.md) | [impl](implementation/f25-insights-load-analyze.md) |
| F26 `edit` metadata surgery (M2.8) | DONE | [spec](features/f26-edit-metadata.md) | [impl](implementation/f26-edit-metadata.md) |
| F27 `trim` crop + rebuild (M2.8) | DONE | [spec](features/f27-trim.md) | [impl](implementation/f27-trim.md) |

## ADRs

| ADR | Decision |
|---|---|
| [0001](architecture/adrs/0001-corpus-format.md) | Corpus format: triplet cases, generated inputs, graded expectations |
| [0002](architecture/adrs/0002-canonical-json.md) | Canonical JSON via RFC 8785; 64-bit string policy |
| [0003](architecture/adrs/0003-defects-as-values-and-modes.md) | Defects as values; modes as one policy switch |
| [0004](architecture/adrs/0004-profile-strategy.md) | Hand-authored core profile + generator; never Garmin files |
| [0005](architecture/adrs/0005-timestamp-policies.md) | Timestamp ordering, timer machine, gap classification, sanity flags |
| [0006](architecture/adrs/0006-encoder-policy.md) | Encoder: canonical wire form, two producers, slot management |
| [0007](architecture/adrs/0007-real-file-pii-policy.md) | Real-file corpus: private tier, PII rules, SDK-sample ban |
| [0008](architecture/adrs/0008-analytics-layer.md) | Analytics layer: sport profiles as data, honest estimators, neutral names |
