# Licensing, Conformance-Suite Patterns, and Naming — Research Report

> Research artifact, 2026-08-17. Produced during chiptime's design phase; informs [../PRD.md](../PRD.md). Practice-based risk assessment, not legal advice.

## Question 1 — FIT Profile licensing

### What the license actually says

The FIT SDK (including Profile.xlsx) ships under the **"Flexible and Interoperable Data Transfer (FIT) Protocol License Agreement"** (current revision "Last updated: October 12, 2022", Kansas law; an older Alberta-law version lives on thisisant.com). Full text is public in Garmin's GitHub repos, e.g. [fit-javascript-sdk/LICENSE.txt](https://github.com/garmin/fit-javascript-sdk/blob/main/LICENSE.txt) and [fit-objective-c-sdk/LICENSE.txt](https://github.com/garmin/fit-objective-c-sdk/blob/main/LICENSE.txt). Key clauses (verified verbatim):

- **Definition**: "Licensed Technology" = "Garmin's FIT SDK that includes documentation describing the FIT protocol and related source code files" — i.e. the license attaches to the SDK artifacts, including Profile.xlsx.
- **Grant (§1)**: "non-exclusive, royalty-free, non-transferable, **non-sublicensable**, limited license to use the Licensed Technology for Licensee's **internal business purposes**, including to **use the FIT protocol in any software created by Licensee**".
- **§2c**: may not "sublicense, assign, **distribute, publish**, transfer or otherwise make available the Licensed Technology … to any third party".
- **§2d (anti-copyleft)**: may not distribute it or derivatives "so that any part of it becomes subject to any license that requires that [it] … be disclosed or distributed in source code form, or that others have the right to modify it" — deliberately GPL/MIT-redistribution-hostile.
- **§2f**: no benchmarking / competitive analysis.
- **§5**: any Modifications/Feedback are perpetually licensed back to Garmin.
- **§9**: terminable immediately on breach, or by either party on 30 days' notice **without cause**; on termination you must delete all copies.

The load-bearing tension: §1 permits *implementing the FIT protocol in your own software*; §2c forbids *redistributing Garmin's SDK files*. The license never addresses generated artifacts derived from Profile.xlsx. A Garmin forum thread asking whether a commercial app may even bundle the compiled Java SDK got **no official Garmin answer** ([thread](https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-connect-mobile-andriod/441413/subject-can-a-commercial-android-app-bundle-the-fit-java-sdk-com-garmin-fit-for-distribution/2051526)).

### Official packages' declared licenses

| Package | Declared license |
|---|---|
| PyPI `garmin-fit-sdk` (21.213.0) | **No license metadata at all** (`license: None`, no classifiers); `pyproject.toml` points at a `LICENSE` file that is **absent from the GitHub repo** ([garmin/fit-python-sdk](https://github.com/garmin/fit-python-sdk) — GitHub shows "license: None") |
| npm `@garmin/fitsdk` (21.213.0) | `"SEE LICENSE IN LICENSE.txt"` → the FIT Protocol License Agreement above |
| [garmin/fit-sdk-tools](https://github.com/garmin/fit-sdk-tools) (publicly hosts **Profile.xlsx**) | LICENSE.txt = same FIT Protocol License (GitHub: `NOASSERTION`) |

So depending on the official packages injects a non-sublicensable, no-redistribution, terminable-at-will, copyleft-incompatible license into your dependency tree.

### How existing OSS parsers handle it

- **python-fitparse** (MIT, ~820★): commits a **generated** `fitparse/profile.py` (~421 KB) under MIT. [`scripts/generate_profile.py`](https://github.com/dtcooper/python-fitparse/blob/master/scripts/generate_profile.py) converts Profile.xls; its header tells the developer to download the SDK themselves ("You can download the SDK at thisisant.com"). **Profile.xlsx is never committed.** No licensing issue has ever been raised in its tracker (searched; only a trivial LICENSE-credits PR).
- **fitdecode** (MIT, ~220★): identical pattern — generated [`fitdecode/profile.py`](https://github.com/polyvertex/fitdecode/blob/master/fitdecode/profile.py) (~583 KB) with header "EXPORTED PROFILE FROM SDK VERSION 21.171 ON 2025-08-04", regenerated via `tools/generate_profile.py`; xlsx not vendored.
- **muktihari/fit** (Go, BSD-3, ~170★): the one project that **does vendor Profile.xlsx** — and explicitly dual-flags it in the README: `internal/cmd/fitgen/Profile.xlsx` and `testdata/from_official_sdk/*` are "licensed under the FIT SDK License. These files are used for code generation and testing only", with a non-affiliation disclaimer; generated Go code is BSD-3 ([repo](https://github.com/muktihari/fit)).
- **GoldenCheetah** (GPL-2.0, ~2,200★): hand-written parser ([src/FileIO/FitRideFile.cpp](https://github.com/GoldenCheetah/GoldenCheetah/blob/master/src/FileIO/FitRideFile.cpp)) with message/field constants transcribed directly into C++; no generation pipeline, no reference to Garmin's SDK license.
- **Concerns actually raised**: [JOSM ticket #8647](https://josm.openstreetmap.de/ticket/8647) is the clearest precedent — a 2013 FIT importer built on Garmin's `fit.jar` was blocked ("This license is definitely not compatible with GPL"), stalled a decade, and was resolved in 2023 by an **independent implementation written from Garmin's public protocol docs** on developer.garmin.com, which are readable with "no click-through license required". In [fq PR #863](https://github.com/wader/fq/pull/863) (MIT tool) only *test-file* licensing was questioned; the decoder itself was written independently and merged. fitparse/fitdecode trackers: silence — ~14 years of shipping generated profiles with no known complaint or enforcement.

### BOTTOM LINE (Q1)

**Do what fitparse/fitdecode do: generate, don't vendor, don't depend.** Concretely, the lowest-risk established practice for an MIT/Apache library:

1. **Never depend on `garmin-fit-sdk` / `@garmin/fitsdk`** — that puts the FIT Protocol License (no sublicensing, no redistribution, §2d anti-open-source clause, at-will termination) inside your dependency tree and breaks your own license's promises.
2. **Never commit Profile.xlsx or any SDK file** to the repo (muktihari does and flags it, but that leaves Garmin-licensed files inside a BSD repo — avoid).
3. **Ship a generator script**; the maintainer downloads the SDK locally, runs it, and commits only the **generated definitions in your own code/data shape** under your license, with a provenance header (SDK version + date), a non-affiliation disclaimer, and a "FIT and Garmin are trademarks of Garmin Ltd." note. The message numbers, field ids, scales and units are functional interface facts needed for interoperability — exactly the material §1 licenses you to use "in any software created by Licensee" — and 14 years of ecosystem practice (fitparse 2011→, fitdecode, fitparse-rs, fit-php-parser, muktihari/fit) shows zero enforcement against it. The public, click-through-free protocol docs (per JOSM 2023) are a documented independent basis if you ever need one.
4. Corollary for the test corpus: **don't vendor official SDK sample .fit files** (the one thing projects that did it felt obliged to flag as Garmin-licensed) — synthesize your own fixtures.
5. Corollary from §2f (no benchmarking): keep published comparative benchmarks/scoreboards to OSS libraries (fitparse, fitdecode, fit-file-parser); characterize the official SDK only via public issue reports, not via benchmarks we run.

## Question 2 — Cross-language conformance suite patterns

### toml-test ([toml-lang/toml-test](https://github.com/toml-lang/toml-test))
- **Layout**: `tests/valid/**` and `tests/invalid/**`, subdirectories per topic (`integer/`, `datetime/`, `string/`, `spec-1.0.0/`…).
- **Case**: valid = pair `name.toml` + `name.json`; invalid = a **single input file only**, "named after the fault it is trying to expose"; pass = decoder rejects.
- **Expected output is *tagged* JSON**: scalars are `{"type": "integer", "value": "42"}` — type name + **value always a JSON string**, avoiding JSON number precision loss.
- **Consumption**: an external Go runner binary drives any implementation as a subprocess: TOML on stdin → tagged JSON on stdout, exit 0; invalid input → non-zero exit. Fully language-agnostic via the process boundary.
- **Versioning**: version-pinned file lists (`tests/files-toml-1.0.0`, `-1.1.0`), `-toml=1.0|1.1` flag, tagged releases; README explicitly tells CI users to pin a tag so "your tests [don't break] on changes to tests in this tool"; a `copy` subcommand vendors the right subset.

### JSON-Schema-Test-Suite ([json-schema-org/JSON-Schema-Test-Suite](https://github.com/json-schema-org/JSON-Schema-Test-Suite))
- **Layout**: `tests/<draft-2020-12|draft-07|…>/*.json`, plus `optional/` and `optional/format/`; `latest` symlink.
- **Case**: self-describing JSON manifest — array of `{description, schema, tests: [{description, data, valid: true|false}]}`. Invalid expectations are just `"valid": false` inline; no separate directory, no exit codes.
- **Consumption**: implementations vendor the data repo "as a git submodule or git subtree" (or npm package) and write a ~50-line native loader for their own test framework. No runner binary at all.
- **Versioning**: per-draft directories frozen over time; old drafts get fewer backports.

### CommonMark ([commonmark/commonmark-spec](https://github.com/commonmark/commonmark-spec))
- **Tests live inside the spec**: `spec.txt` embeds 500+ ` ```example ` blocks — markdown input, a lone `.` separator line, expected HTML.
- **Consumption, two modes**: `spec_tests.py --program $PROG` pipes input to any executable's stdin and diffs stdout (with HTML normalization); `--dump-tests` exports everything as JSON (`{markdown, html, section, example}`) for native in-language runners.
- **Versioning**: the suite version *is* the spec version.

### BOTTOM LINE (Q2) — patterns to copy for a FIT corpus

1. **Triplet-per-case with a metadata manifest** (toml-test pairing + JSON-Schema self-description): `cases/<category>/<name>.fit` + `<name>.expected.json` + `<name>.meta.json`, where meta carries the defect description, provenance (synthesized-by script + params), profile/spec version, and — crucially for FIT — a *graded* expectation, since FIT failure isn't binary like TOML: `{"expect": "reject", "error_class": "header_crc_mismatch"}` vs `{"expect": "partial", "warnings": ["truncated_last_record"], "records_decoded": 1204}` vs `{"expect": "ok"}`. Name corrupt cases after the fault, toml-test style.
2. **Typed/tagged canonical JSON for expected output** (toml-test's single best idea): FIT has uint64s, invalid-value sentinels, scale/offset transforms, and semicircle coordinates — represent risky fields as type-tagged with string-encoded numerics (and ideally both raw and scaled value) so Python and JS runners compare without float/bigint trapdoors.
3. **Data-only repo + native runners now, subprocess protocol later** (JSON-Schema first, toml-test as the growth path): for a two-language project we control, keep the corpus as a data-only directory and write one thin pytest loader and one vitest/node loader — cheapest and CI-friendly. Keep the corpus free of implementation code, version it with **tagged releases that implementations pin** (toml-test's CI advice), and ship a files-list manifest for subsetting. If third-party implementations ever want in, add the toml-test-style contract: `.fit` on stdin → canonical JSON on stdout, non-zero exit + error class for reject cases — CommonMark's `--dump-tests` shows both modes coexist fine.

## Question 3 — Naming: "chiptime"

- **PyPI**: `https://pypi.org/pypi/chiptime/json` → **HTTP 404. Available.**
- **npm**: `https://registry.npmjs.org/chiptime` → **`{"error":"Not found"}`. Available.**
- **GitHub**: no significant project uses the name. 34 name matches, but nearly all belong to a personal **user account named `chiptime`** (0–1-star learning repos) plus a few tiny unrelated repos. Consequence: `github.com/chiptime` the *username/org* is taken; `yourname/chiptime` is unclaimed and unconflicted.
- **Trademark-ish landscape**: "chip time" is the **generic race-timing term** for net time ([Wikipedia: Chip timing](https://en.wikipedia.org/wiki/Chip_timing)), and the running world is full of descriptive-name timing companies — the closest is **Chiptime Results** ([chiptimeresults.com](https://chiptimeresults.com/our-services/)), a US race-timing services outfit. A generic/descriptive term in that field has weak trademark strength, and a file-parsing library is a different product category from event-timing services — low practical risk, and arguably a nice thematic fit for a sports-data library.

### BOTTOM LINE (Q3)
**"chiptime" is free on both PyPI and npm — register both early.** No software collision exists anywhere; the only footnotes are a squatted GitHub *username* (use `<org>/chiptime`, not a `chiptime` org) and a small US race-timing company "Chiptime Results" in an adjacent-but-distinct services category.

## Sources
- https://github.com/garmin/fit-javascript-sdk/blob/main/LICENSE.txt (full FIT Protocol License text, Oct 2022 revision)
- https://github.com/garmin/fit-objective-c-sdk/blob/main/LICENSE.txt
- https://github.com/garmin/fit-python-sdk (no license file; PyPI metadata empty)
- https://github.com/garmin/fit-sdk-tools (Profile.xlsx under FIT license)
- https://registry.npmjs.org/@garmin%2ffitsdk / https://pypi.org/pypi/garmin-fit-sdk/json
- https://www.thisisant.com/developer/ant/licensing/flexible-and-interoperable-data-transfer-fit-protocol-license (older license revision)
- https://github.com/dtcooper/python-fitparse (+ scripts/generate_profile.py, fitparse/profile.py)
- https://github.com/polyvertex/fitdecode (+ tools/generate_profile.py, fitdecode/profile.py)
- https://github.com/muktihari/fit (dual-flagged vendored Profile.xlsx)
- https://github.com/GoldenCheetah/GoldenCheetah/blob/master/src/FileIO/FitRideFile.cpp
- https://josm.openstreetmap.de/ticket/8647 (GPL incompatibility discussion + 2023 resolution)
- https://github.com/wader/fq/pull/863 (test-file licensing discussion)
- https://forums.garmin.com/apps-software/mobile-apps-web/f/garmin-connect-mobile-andriod/441413/subject-can-a-commercial-android-app-bundle-the-fit-java-sdk-com-garmin-fit-for-distribution/2051526
- https://github.com/toml-lang/toml-test (README incl. tagged-JSON encoding section)
- https://github.com/json-schema-org/JSON-Schema-Test-Suite
- https://github.com/commonmark/commonmark-spec
- https://pypi.org/pypi/chiptime/json / https://registry.npmjs.org/chiptime (availability checks)
- https://en.wikipedia.org/wiki/Chip_timing / https://chiptimeresults.com/our-services/
