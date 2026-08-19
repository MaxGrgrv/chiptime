# chiptime

**Recovery-grade FIT file processing.** Parse anything, lose nothing silently, explain everything. Zero runtime dependencies.

Every other open-source FIT parser stops at the first bad byte. chiptime resynchronizes mid-file, salvages truncated files, rebuilds missing session summaries, and can write the result back out as a valid, uploadable `.fit` — with a machine-readable provenance trail for every repair.

```python
import chiptime

result = chiptime.parse("broken.fit")  # lenient: recover + annotate
result.recovery  # what was salvaged
result.activity.sessions[0].records.stream("power")  # 0 is real, None is absent
result.to_canonical_json()  # RFC 8785 — byte-identical every run

fixed = chiptime.repair("broken.fit")  # → a valid .fit
```

```bash
chiptime parse ride.fit --json      # agent exit codes: 0/2/3/4/64
chiptime repair broken.fit -o fixed.fit
chiptime validate fixed.fit --platform garmin-connect
chiptime inspect weird.fit          # wire-level forensics
```

- Three modes: `strict` / `lenient` / `forensic` (forensic never drops data)
- Sentinels → null before any statistics; zero ≠ null, always
- Deterministic canonical JSON; errors carry stable codes + suggested next steps
- Conformance corpus: 104-item edge-case taxonomy, golden-file tested
- Optional extras: `chiptime[pandas]` for DataFrames; `chiptime.metrics` for mean-max curves, zone time, SWOLF

Docs, taxonomy, corpus and research: https://github.com/MaxGrgrv/chiptime

chiptime is an independent project, not affiliated with or endorsed by Garmin. FIT and Garmin are trademarks of Garmin Ltd. This package ships no Garmin SDK files.
