---
description: chiptime CLI reference: parse, inspect, repair, validate, analyze, codes — flags and stable exit codes.
---

# CLI reference

```bash
chiptime <command> [options]
```

Exit codes are a stable contract: **0** clean · **2** recovered with data loss ·
**3** unusable input · **4** not FIT · **64** usage error.

## `chiptime parse FILE`

Human summary by default; canonical JSON with `--json`.

| Flag | Effect |
|---|---|
| `--mode {strict,lenient,forensic}` | Parse policy (default `lenient`) |
| `--json` | Emit canonical JSON (RFC 8785) on stdout |
| `-o, --output PATH` | Write JSON to a file |
| `--strip-pii` | Drop GPS coordinates and athlete identity fields |
| `--include-raw` | Include raw wire values alongside decoded ones |
| `--no-unknown` | Omit unknown messages from output |

## `chiptime inspect FILE [--limit N]`

Wire-level frame table — headers, definitions, data frames, CRCs, skipped bytes.
Forensics for files that make no sense.

## `chiptime repair FILE -o OUT [--mode {lenient,forensic}]`

Salvage → synthesize → self-check → write a valid `.fit`.

## `chiptime validate FILE [--platform {strict-spec,garmin-connect,strava}]`

Platform-acceptance findings (severity, code, detail) before you upload.

## `chiptime analyze FILE`

Per-sport workout report + insights (the optional analytics layer).

| Flag | Effect |
|---|---|
| `--json` / `-o PATH` | Deterministic machine-readable report |
| `--mode {...}` | Parse policy for the underlying parse |
| `--ftp W` | Enables intensity ratio + `power+ftp` load |
| `--max-hr N --resting-hr N` | Enables TRIMP load |
| `--sex {male,female}` | TRIMP coefficient (unset = labeled male default) |
| `--hr-zones a,b,c,...` | Ascending bpm upper bounds → HR zone times |
| `--power-zones a,b,c,...` | Ascending W upper bounds → power zone times |

## `chiptime codes`

Print the full error / warning / provenance registry — same content as the
[codes reference](codes/index.md).
