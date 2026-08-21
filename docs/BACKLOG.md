# chiptime — Backlog

Items deferred during critique cycles and reviews. Deferred doesn't mean forgotten: every entry has a reason and a revisit trigger.

Note: the parser-behavior backlog is [edge-case-taxonomy.md](edge-case-taxonomy.md) (priority tiers at the bottom). This file tracks scope cut or deferred during planning and critique.

| Item | Feature | Why deferred | When to revisit |
|---|---|---|---|
| Data-frame re-anchoring in resync (depth-3 chained validation) | F5 | Definition-only re-anchoring is safe; data headers too low-entropy without deeper validation | When corpus gains real-device garbage-block files that definition-anchoring fails to salvage |
| DST/timezone-crossing depth (#47 full) | F8 | Needs real multi-zone fixtures; UTC stream already immune by construction | When ★ own-archive travel files land |
| Platform dedup identity + size limits (#100/#101, downsampling) | F14 | Unverifiable without real upload probes against platform accounts | When platform acceptance testing becomes possible |
| Opt-in HR/power spike interpolation repairs (#62 depth) | F15 | Flags-only shipped; interpolation is opt-in repair territory needing real-device fixtures | When ★ own-archive files land |
| Bulk columnar decode path (records bypass per-message dicts into streams) | F20 | The next perf multiple (past 1.7x) is architectural, not micro; FieldValue-per-field IS the lossless layer's current contract | Design alongside M3 parity work |
| Generic component-expansion engine (37 profile sources, >32-bit stores) | F22 | hr + csd + accumulated_power cover the evidence-heavy cases; engine needs generator to emit Components/Bits columns | When a real file needs a 4th expansion (audit row 14) |
| Generic subfield engine from profile subfield rows | F22 | product resolution covers the hot case; engine needs generator subfield parsing | With component engine (same generator work) |
| HR-merge into record timeline (SDK-style) | F22 | Message-level expansion shipped; timeline merge is semantic layering on top | When hr-carrying real files land in private corpus |
| Vendor naming divergence registry (Suunto sport 26→paragliding; taxonomy G) | F22 | Needs per-vendor evidence files | Device-quirk registry work (M4) |
| VIRB timestamp_correlation support (fitdecode#6) | F22 | Niche action-camera domain | When a VIRB file lands |
| Zone-based interval classification (per-zone min durations, intervals.icu-style) | F24 | Relative bands work threshold-free; zone rules need AthleteSettings adoption evidence | When users supply zones and ask for Z4/Z5 rep labeling |
| Semantic Lap fields for lap_trigger/wkt_step_index | F24 | Would change canonical parse output (corpus-wide regen); analytics reads raw messages instead | When a second consumer needs triggers outside metrics |
| `chiptime edit --validate PLATFORM` convenience flag | F26 | `chiptime validate` composes fine; one flag less | If users report the two-step flow is friction |
| Auto-derive `sub_sport` when sport changes | F26 | Inference into metadata = the non-goal the PRD forbids; warn instead | Never, unless the warning proves insufficient in practice |

