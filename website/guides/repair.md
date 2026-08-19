---
description: Fix a corrupted or truncated FIT file so Garmin Connect and Strava accept it: chiptime repair salvages, synthesizes, and self-checks.
---

# Repair crash files

The most common FIT tragedy: a device crashes four hours into a ride. The file holds
every sample up to the crash, but its header says "0 bytes", the CRC is wrong, and the
final session/activity messages were never written. Platforms reject it; the ride is
"lost".

## One call

```bash
chiptime repair crashed.fit -o fixed.fit
chiptime validate fixed.fit --platform garmin-connect   # verify before upload
```

```python
fixed = chiptime.repair("crashed.fit")
fixed.data                 # complete, valid .fit bytes
fixed.output_strict_ok     # self-check: the output parses in strict mode
fixed.provenance           # exactly what was salvaged and synthesized
open("fixed.fit", "wb").write(fixed.data)
```

## What repair actually does

1. **Salvage** — parse the input in recovery mode: fix the header, resync past
   damage, keep every readable message.
2. **Synthesize** — rebuild what platforms require but the crash destroyed:
   session and activity messages recomputed from the records, correct sizes and CRCs.
   Implausible fields that would make platforms reject the file (like a 1989
   `local_timestamp` some trainers write) are dropped — and logged.
3. **Self-check** — re-parse the output in `strict` mode. `output_strict_ok` is that
   verdict; repair never hands you a file it can't read back flawlessly itself.

Everything synthesized is marked in `provenance` — a repaired file never pretends
data was recorded when it was reconstructed.

## Honesty boundary

Repair reconstructs *containers* (headers, totals, CRCs, required messages) from data
that exists. It never fabricates *samples*: if the last hour wasn't written, the
repaired file is an honest shorter ride, not an imagined full one.

## Validate against platforms

```python
from chiptime.validate import validate

findings = validate("fixed.fit", platform="garmin-connect")   # or "strava", "strict-spec"
for f in findings:
    print(f.severity, f.code, f.detail)
```

The platform profiles encode the *observed* acceptance rules of each service — the
checks that actually make uploads fail.
