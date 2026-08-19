# Implementation: F22 — Issue-Mining Hardening

> Feature Spec: [../features/f22-issue-mining-hardening.md](../features/f22-issue-mining-hardening.md)
> Audit: [../research/issue-mining-audit.md](../research/issue-mining-audit.md)

## Summary
Eleven parsers' complete issue histories audited (30 consolidated bug classes); nine evidence-anchored fixes landed. Each fix cites the wild specimen it answers; each has a corpus case and/or test named after the source issue. A tenth, unplanned fix fell out of writing the tests: the semantic layer was resurrecting device-relative timestamps from raws into fake 1990 datetimes — decode's honesty was being bypassed one layer up.

## The nine (+1) fixes
| Fix | Evidence | Where |
|---|---|---|
| timestamp_16 rolling merge (monotone across 0x10000) | fitdecode#28, fitparse#46 | decode `_merge_timestamp16` + temporal/timestamp16-rollover |
| hr event_timestamp_12 expansion (12-bit LSB stream, 0xFFF rollover, /1024 s) | fitparse#69/#122, muktihari#474 | decode `_expand_hr` + sensors/hr-event-timestamp-12 |
| Float sentinel = exact all-ones bytes (silent) vs genuine NaN (warned); encoder emits exact pattern | muktihari#39, fit_tool#35 | decode scalar+array paths, encode `_data`, builder + protocol/float-sentinel-vs-nan |
| left_right_balance(_100) bit decode → right_balance_pct | fitdecode#38, swift#13, fit-parser#4, easy-fit#31, tormoder#86 | decode `_decode_balance` + sensors/left-right-balance |
| product → garmin_product/favero_product subfield | fitparse PR#131 | decode `_resolve_product`; existing snapshots now name "edge_530"/"fr965" |
| Embedded-NUL string arrays; replacement-charred tail after valid segments = padding junk | muktihari#623/#436 | decode `_string` + protocol/multi-string-arrays |
| timestamp declared as byte[4] reassembled per definition endianness | fitdecode#33 (Xiaomi pipeline) | decode + temporal/timestamp-as-bytes |
| Relative timeline preserved: derived elapsed from raw deltas when wall-clock absent | fitparse#3/#6, taxonomy #39 | semantics `_derive_relative_elapsed` + temporal/system-time-only |
| Resync validator field cap 100→255 (>85-field definitions are normal) | tormoder#43, muktihari#77 | frames validator |
| **Bonus:** `_dt` guards the relative ceiling — no more fabricated 1990 datetimes from raws | found by F22's own test | semantics build |

## Verification
238 tests green · 71 public + 6 private conformance cases · soak vs 66 real files: 0 contract violations, 0 GC-invalid repairs · ruff/mypy clean.

## Lessons Learned
The audit's three cross-cutting lessons (alignment is sacred; fixes un-fix without corpora; the profile is data not truth) were already chiptime's architecture — the mining validated the design more than it changed it: 21 of 30 classes were handled before this feature existed.
