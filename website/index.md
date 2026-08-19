---
description: Recovery-grade FIT file processing for Python: parse corrupted .fit files, repair crash files for upload, analyze workouts. Zero dependencies, deterministic, MIT.
---

<div class="ct-hero" markdown>

# Parse anything.<br><span class="ct-grad">Lose nothing silently.</span>

<p class="ct-sub">chiptime is recovery-grade FIT file processing: hand it any workout file — pristine or mangled — and it returns everything genuinely in there, explains every decision it made, and never invents what isn't.</p>

<div class="ct-actions" markdown>
[Get started](getting-started.md){ .md-button .md-button--primary }
[API reference](reference/api-core.md){ .md-button }
[:material-star: Star on GitHub](https://github.com/MaxGrgrv/chiptime){ .md-button .ct-star }
</div>

</div>

Every sports watch and bike computer saves workouts as `.fit` files — and in the real world those files are often imperfect: devices crash mid-ride, batteries die during the save, firmware writes impossible timestamps, sensors drop out. Most parsers handle the happy path and fail the rest: they crash, silently skip data, or quietly make things up. chiptime is built for the rest.

```python
import chiptime

result = chiptime.parse("inProgressActivity.fit")   # truncated mid-ride crash file
result.ok                                           # True — salvaged
result.recovery.recovered_records                   # what came back
result.activity.sessions[0].rebuilt                 # True: session rebuilt from records
result.to_canonical_json()                          # deterministic, byte-stable JSON
```

## Why chiptime

<div class="grid cards" markdown>

- :material-shield-check:{ .lg .middle } **Never loses data silently**

    ---

    Every drop, repair, and reinterpretation is recorded in a machine-readable
    `provenance` log on the output. Silent data loss is treated as the cardinal sin.

- :material-repeat:{ .lg .middle } **Deterministic to the byte**

    ---

    Same input bytes → byte-identical canonical JSON, across runs, machines, and
    operating systems. Safe to diff, cache, and test against.

- :material-wrench:{ .lg .middle } **Repairs, not just reads**

    ---

    `chiptime repair` salvages a damaged file and writes a fresh, valid `.fit`
    that Garmin Connect and Strava accept — verified against their validators.

- :material-chart-line:{ .lg .middle } **Sport-aware analytics**

    ---

    `chiptime analyze` speaks each sport's language: min/km for runs, watts for
    rides, min/100m and sets for swims, /500m splits for rowing — computed only
    from real evidence, never estimated.

- :material-robot:{ .lg .middle } **Built for agents**

    ---

    Stable machine codes for every error and insight, meaningful exit codes,
    canonical JSON, and generated reference docs. AI agents are first-class users.

- :material-scale-balance:{ .lg .middle } **Honest by contract**

    ---

    `null` means the sensor said nothing; `0` means it said zero. Unknown fields
    are preserved, not crashed on. If data is truly gone, chiptime says so.

</div>

## Install

```bash
pip install chiptime
```

Python ≥ 3.11, **zero runtime dependencies**. `pip install "chiptime[pandas]"` adds DataFrame export.

## Sixty seconds of chiptime

```bash
chiptime parse ride.fit                 # human summary
chiptime parse ride.fit --json          # canonical JSON for machines
chiptime repair crashed.fit -o fixed.fit
chiptime validate fixed.fit --platform garmin-connect
chiptime analyze ride.fit --ftp 250     # per-sport report + insights
```

Continue with [Getting started](getting-started.md), or jump straight to the
[Python API reference](reference/api-core.md).

<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "chiptime",
  "description": "Recovery-grade FIT file processing: parse anything, lose nothing silently, explain everything. Parses, repairs, validates, and analyzes Garmin/Wahoo/Zwift .fit workout files, including corrupted and truncated ones.",
  "applicationCategory": "DeveloperApplication",
  "operatingSystem": "Any",
  "offers": {"@type": "Offer", "price": "0"},
  "license": "https://opensource.org/licenses/MIT",
  "programmingLanguage": "Python",
  "url": "https://maxgrgrv.github.io/chiptime/",
  "codeRepository": "https://github.com/MaxGrgrv/chiptime"
}
</script>
