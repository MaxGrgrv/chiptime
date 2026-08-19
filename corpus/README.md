# chiptime conformance corpus

The language-agnostic conformance contract (ADR-0001). Every edge case in
[docs/edge-case-taxonomy.md](../docs/edge-case-taxonomy.md) maps to at least one case here;
every implementation (Python today, JavaScript at M3) must produce byte-identical canonical
output for every case.

## Case layout

```
cases/<category>/<slug>/
  input.fit        bytes under test — generated, NEVER hand-edited (sha256-guarded)
  expected.json    exact canonical output bytes, lenient mode (RFC 8785 — ADR-0002)
  case.json        metadata + deterministic build pipeline
```

### case.json

```jsonc
{
  "slug": "truncated-mid-record",
  "category": "structural",
  "taxonomy": [2],                  // items from docs/edge-case-taxonomy.md
  "tier": 1,
  "expect": "partial",              // ok | partial | reject   (lenient-mode grade)
  "modes": {                        // per-mode expectations, asserted by the runner
    "strict": "raise:FIT_TRUNCATED",
    "lenient": "partial",
    "forensic": "partial"
  },
  "build": [                        // deterministic pipeline (gen_all.py)
    {"op": "seed", "name": "ride_smooth"},
    {"op": "truncate", "at": 1234}
  ],
  "input_sha256": "…",              // recorded by gen_all --update; verified in CI and at test time
  "source": "synthetic",            // synthetic | own-archive | donated
  "notes": "battery death mid-write"
}
```

Grades: `ok` = parses clean (warnings allowed) · `partial` = usable output with recovery/data
loss recorded in provenance · `reject` = no usable output (`ok: false`), typed error present.

## Tools

- `tools/build_fit.py` — deterministic synthetic FIT writer + named seeds. **Independent of
  chiptime by design** (shared bugs would cancel out — ADR-0001 §3).
- `tools/corrupt.py` — pure byte-level corruption/wrapping ops with explicit parameters.
- `tools/gen_all.py` — regenerate/verify all inputs (`--update`), snapshots (`--expected`),
  and `MANIFEST.json`.

## Rules

1. Inputs are reproducible: `case.json` fully determines `input.fit`. CI re-verifies sha256.
2. Snapshots change only deliberately: regenerating `expected.json` is done in the same PR as
   the behavior change, and the diff is reviewed.
3. No Garmin SDK sample files, ever (license — see docs/research/licensing-conformance-naming.md).
   Allowed sources: synthetic, own-archive (PII-stripped, consented), donated (with consent note).
4. Keep inputs small (tens of records) so snapshots stay reviewable.
