---
description: Using chiptime from AI agents and pipelines: exit codes, stable machine codes, canonical JSON, llms.txt, and context-window guidance.
---

# Built for agents

chiptime treats AI agents as first-class consumers. If you're wiring it into an
automated pipeline or an LLM tool loop, everything you need is machine-readable
and stable.

## Exit codes route your control flow

| Exit | Meaning | What an agent should do |
|---|---|---|
| 0 | Parsed clean (warnings allowed) | Proceed |
| 2 | Parsed with recovery / data loss | Proceed; inspect `provenance[]` |
| 3 | Structurally FIT, nothing salvageable | Surface the error; try `repair`/`forensic` |
| 4 | Not a FIT file | Route to a different parser |
| 64 | Usage error | Fix the invocation |

## Every problem has a code

Errors, warnings, and provenance entries carry stable machine codes, a human
sentence, and — where applicable — a suggested flag to handle them:

```json
{
  "code": "TIMESTAMP_BEFORE_2010",
  "detail": "record timestamp 1989-12-31 precedes plausible device era",
  "suggestion": "treat as relative; see provenance TIMESTAMP_REINTERPRETED"
}
```

`chiptime codes` prints the full registry; the same registry generates the
[codes reference](../reference/codes/index.md).

## Canonical JSON is cache-safe

`parse --json` output is RFC 8785 canonical: same file → same bytes, on any machine.
Hash it, diff it, memoize on it. The schema is versioned (`chiptime_schema: 1`) and
the local file path is never serialized.

## Insight codes for analysis

`chiptime analyze FILE --json` emits a deterministic report whose insights carry
stable codes (`PACING_NEGATIVE_SPLIT`, `HR_DRIFT_HIGH`, ...) with numeric
`evidence`, and whose derived numbers carry a `basis` string
(`power+ftp`, `laps:manual`, `detected:power-steps`). Analyses lacking inputs land
in `omissions[]` with the reason — the report never silently guesses.

## Context-window economics

Full canonical JSON of a long ride is megabytes — the analyze report is ~1–2 KB.
For LLM consumption: feed the *report*, keep the full JSON on disk, and let the
model request specific streams when needed.

## llms.txt

The site ships `/llms.txt` (curated index + behavioral rules for agents,
generated at build) and `/llms-full.txt` (the entire docs corpus in one
markdown file). Start there when indexing chiptime for a tool or RAG corpus.

## The generated reference

The complete agent-facing contract — every code, the output schema, exit codes —
lives on one page, generated from the code registries:

[Codes registry →](../reference/codes/index.md)
