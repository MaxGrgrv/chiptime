---
description: How to store FIT parse output: measured JSON sizes, gzip ratios, Parquet export, and when determinism means you need not store JSON at all.
---

# Storing the output

Measured on real files (a 5-hour ride, a full-distance triathlon, a pool swim), the
canonical JSON is 3–7× the `.fit` size — dominated by record streams, and on
HRV-rich files by the raw message list. That shapes a clear set of patterns.

## The zeroth rule: you may not need to store JSON at all

Parsing is **deterministic by contract**: the canonical JSON is a pure derivation of
the file bytes. Archive the original `.fit` (it is the most compact and the most
faithful form) plus the chiptime version, and regenerate output on demand.
Determinism *is* the storage optimization.

## Pick the shape for the job

| Use case | Shape | Typical size (5 h ride) |
|---|---|---|
| Archive | the original `.fit` | 333 KB |
| Interchange / audit | canonical JSON, gzipped | 1.2 MB → 268 KB |
| Analytics | streams → pandas / Parquet | streams only |
| Index / dashboard / LLM context | summary (no per-second data) | tens of KB |
| "What should I know about this workout?" | `analyze --json` report | ~1–2 KB |

## Compression

Canonical JSON is repetitive by design (sorted keys, columnar arrays) and compresses
extremely well — gzip reaches 8–22% of the raw JSON, typically *below* the original
`.fit` size:

```bash
chiptime parse ride.fit --json | gzip > ride.json.gz
```

## Analytics: go columnar

Streams are already column-oriented. For serious analysis, export once to a columnar
format and query with pandas/DuckDB/Polars:

```python
df = result.activity.sessions[0].records.to_pandas()   # chiptime[pandas]
df.to_parquet("ride.parquet")
```

`None` stays `NaN`-distinct from `0` — the zero-vs-null contract survives the trip.

## A sane pipeline

```text
inbox/*.fit  ──►  archive/ (originals, immutable)
                  │
                  ├─►  chiptime analyze --json  ─►  index DB (KBs per workout)
                  └─►  on demand: parse --json / to_pandas() for deep dives
```
