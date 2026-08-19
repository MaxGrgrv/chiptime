# Feature: F22 — Issue-Mining Hardening (M2.6)

> Status: DONE

## Purpose
Close every genuine gap surfaced by auditing chiptime against the complete bug histories of eleven FIT parsers (docs/research/issue-mining-audit.md): nine fixes, each anchored to real-world issue evidence.

## Taxonomy Coverage
| Fix | Evidence | Taxonomy |
|---|---|---|
| timestamp_16 rollover merge | fitdecode#28, fitparse#46, tormoder#77 | new sub-case of #36/#48 family |
| hr event_timestamp_12 expansion | fitparse#69/#122, muktihari#474 | #29 depth |
| Float sentinel ≠ NaN (decode silent/warn split + encoder exact pattern) | muktihari#39, fit_tool#35 | #26/#35 refinement |
| left_right_balance(+_100) bit decode | 5 repos | #65 |
| product → garmin_product/favero_product subfield | fitparse PR#131 | #31 slice |
| Embedded-NUL string arrays → lists | muktihari#623 | #33 depth |
| Resync validator field cap 100→255 | tormoder#43/muktihari#77 (>85-field defs are normal) | #10 robustness |
| timestamp-as-byte[4] reassembly | fitdecode#33 (Xiaomi pipeline) | #17/#88 class |
| Relative-timestamp timeline preservation | fitparse#3/#6, taxonomy #39's own words | #39 completion |

## Acceptance Criteria
- [x] Each fix has a corpus case and/or unit test citing its evidence issue
- [x] All prior 64 cases byte-identical except where snapshots legitimately gain fields (regenerated deliberately)
- [x] Soak + full gates green

## Critique & Assessment
- **Alternatives considered:** generic component/subfield engines now (rejected: the two evidence-heavy instances — hr, product — are targeted here; engines go to BACKLOG with the generator's skipped subfield/component columns as the data source). Record-timeline HR merge (SDK-style) — BACKLOG; expansion at message level is the honest first step.
- **Contract check:** every expansion/reassembly emits provenance or warnings; float sentinel silence is *removing* a spurious warning (sentinels are normal absence); nothing fabricated.
- **Final decision:** APPROVE

## Related
- Research: [../research/issue-mining-audit.md](../research/issue-mining-audit.md)
- Implementation: [../implementation/f22-issue-mining-hardening.md](../implementation/f22-issue-mining-hardening.md)
