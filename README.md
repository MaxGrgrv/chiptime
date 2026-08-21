<h1 align="center">chiptime</h1>

<p align="center"><b>Parse anything. Lose nothing silently. Explain everything.</b></p>

<p align="center">
  <a href="https://github.com/MaxGrgrv/chiptime/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/MaxGrgrv/chiptime/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-blue">
  <img alt="Zero dependencies" src="https://img.shields.io/badge/dependencies-0-brightgreen">
  <img alt="MIT" src="https://img.shields.io/badge/license-MIT-black">
  <a href="https://maxgrgrv.github.io/chiptime/"><img alt="Docs" src="https://img.shields.io/badge/docs-chiptime-635bff"></a>
</p>

Every sports watch and bike computer saves workouts as `.fit` files — and real files
are often imperfect: devices crash mid-ride, batteries die during the save, firmware
writes impossible timestamps, sensors drop out. **chiptime is recovery-grade FIT
processing**: hand it any file, pristine or mangled, and it returns everything
genuinely in there, explains every decision it made, and never invents what isn't.

## The story in four lines

```python
import chiptime

result = chiptime.parse("inProgressActivity.fit")   # crashed 4 hours into a ride
result.ok                                           # True — the ride is back
result.activity.sessions[0].rebuilt                 # session rebuilt from the records
open("fixed.fit", "wb").write(chiptime.repair("inProgressActivity.fit").data)
```

The repaired file passes platform validation and uploads. The parse result carries a
complete paper trail — `provenance[]` lists every byte skipped, every field repaired,
every value reinterpreted. Silent data loss is treated as the cardinal sin.

## What you get

- **Parse** — sessions, laps, swim lengths, and per-second columnar streams; totals
  both as the device declared them *and* recomputed from the data, with
  disagreements surfaced. Gaps classified (auto-pause ≠ corruption). Unknown
  messages and fields preserved, never fatal.
- **Repair** — salvage a damaged file and write back a valid `.fit`, self-checked by
  re-parsing in strict mode. Honest by design: containers are reconstructed, samples
  never fabricated.
- **Validate** — platform-acceptance checks before you upload.
- **Analyze** — sport-aware analytics that speak each discipline's language:

```text
$ chiptime analyze zwift_workout.fit --ftp 250
session 1: cycling/virtual_activity
  55:11 · 29.61 km · avg 164 W · weighted 175 W · avg HR 136
  structure [laps:manual]: 3 x 10:00 @ 194 W rest 3:24
  load 45 [power+ftp]
  PACING_NEGATIVE_SPLIT: Second half 7.6% faster than the first.
```

Runs get min/km and splits, swims get min/100m and sets, rowing gets /500m splits.
Thresholds and zones come from you or the file — never estimated. Anything not
computable is listed with its reason instead of guessed.

## The contract

1. **Never lose data silently** — every drop and repair lands in `provenance[]`.
2. **Deterministic** — same bytes in, byte-identical canonical JSON out, on every
   machine. Safe to hash, diff, cache, and test against.
3. **Zero ≠ null, always** — coasting is `0` W (real); dropout is `null` (absent).
   FIT sentinels become `null` before any statistic is computed.
4. **Honest non-recovery** — what's truly gone is reported gone.

The contract is enforced by a conformance corpus built from a **104-item edge-case
taxonomy**: 72 public cases (plus a private real-device tier) with committed
expected outputs, gating every change in CI. The corpus is also the cross-language
contract — the TypeScript implementation (in progress) must match Python
byte-for-byte.

## Install

```bash
pip install chiptime
```

Python ≥ 3.11 · **zero runtime dependencies** · fully typed (`mypy --strict`,
`py.typed`) · `pip install "chiptime[pandas]"` adds DataFrame export.

```bash
chiptime parse ride.fit --json      # canonical JSON
chiptime repair crashed.fit -o fixed.fit
chiptime validate fixed.fit --platform garmin-connect
chiptime analyze swim.fit
chiptime codes                      # every machine code, explained
```

## Built for agents too

Stable machine codes for every error, warning, provenance entry, and insight; exit
codes that route control flow; deterministic JSON; [`llms.txt`](https://maxgrgrv.github.io/chiptime/llms.txt)
and full-corpus markdown for indexing. If your consumer is a program or an LLM, the
interface was designed with it in mind.

**Docs:** [maxgrgrv.github.io/chiptime](https://maxgrgrv.github.io/chiptime/) —
[getting started](https://maxgrgrv.github.io/chiptime/getting-started/) ·
[API reference](https://maxgrgrv.github.io/chiptime/reference/api-core/) ·
[migration guides](https://maxgrgrv.github.io/chiptime/switch/) ·
[the contract](https://maxgrgrv.github.io/chiptime/concepts/contract/)

## Status

`0.7.0` — Python implementation live: decode + recovery + repair + validation +
analytics, plus the file-surgery verbs (`edit`, `trim`, `reveal`/`scrub`). 371
tests, validated against 66 real device files with zero contract violations.

**In progress (M3):** the TypeScript twin on the shared corpus. The canonical
serializer and number kernel are built and differentially tested against CPython;
parsing lands next. Nothing is published to npm yet — see
[the M3 plan](docs/m3-typescript-plan.md).

MIT. Not affiliated with Garmin; FIT profile tables are generated by our own
tooling — no Garmin SDK code or files are included.
