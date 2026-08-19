---
description: Why chiptime output is byte-identical everywhere, how that is enforced, and what it buys: testability, caching, cross-language parity.
---

# Determinism

**Same file in, same bytes out — always.** This is invariant #2 and the property
everything else leans on.

## What exactly is guaranteed

`parse(bytes).to_canonical_json()` is a pure function: identical across runs,
Python versions in support, machines, and operating systems. The JSON is RFC 8785
(JCS) canonical — sorted keys, fixed number formatting, no incidental whitespace.

## How it's achieved

- No wall-clock reads, no randomness, no environment leakage into output
  (the local file path is never serialized).
- Every iteration that could depend on insertion order is explicitly sorted.
- Numbers with representation ambiguity (64-bit integers beyond 2^53−1) are emitted
  as decimal strings by policy.
- Analytics constants (band thresholds, windows) are named module constants — the
  TypeScript port copies them verbatim.

## What it buys you

- **Trust through tests** — the corpus commits expected bytes; any behavioral change
  is a visible diff, reviewed like code.
- **A cross-language contract** — the TypeScript implementation must match Python
  byte-for-byte on the same corpus. "Ports" usually drift; a byte-exact corpus makes
  drift impossible to hide.
- **Cache and dedupe for free** — hash the output; identical files are identical
  bytes.
- **Storage economics** — you can archive only the `.fit` and regenerate JSON at
  will. [Storing the output →](../guides/storage.md)

## Verified in CI

Every corpus case is parsed twice per run and must equal itself; the whole suite
must equal its committed expectations. The pre-push hook runs the same gate locally.
