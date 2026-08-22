#!/usr/bin/env python3
"""CLI parity: stdout bytes and exit codes, across every corpus case (F37).

Run from repo root:  uv run --project python python scripts/check_cli_parity.py

The CLI is the agent contract — `docs/for-agents.md` publishes the exit codes and
promises `--json` emits canonical bytes on stdout. So the comparison is the whole
of stdout, byte for byte, plus the exit code, for every invocation.

Both sides run in-process (Python calls `cli.main`, TypeScript calls the exported
`main` with injected writers) rather than spawning a process per case: 72 cases x
several invocations is thousands of spawns, and the thing under test is the output,
not the shell plumbing.

Exit 0 = every invocation agrees.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python" / "src"))

from chiptime.cli import main as py_main  # isort:skip

# Invocation shapes, applied to every corpus case.
INVOCATIONS = [
    ["parse", "{file}"],
    ["repair", "{file}", "-o", "{out}"],
    ["validate", "{file}"],
    ["validate", "{file}", "--platform", "garmin-connect"],
    ["validate", "{file}", "--platform", "strava"],
    ["analyze", "{file}"],
    ["analyze", "{file}", "--json"],
    ["analyze", "{file}", "--json", "--ftp", "250", "--max-hr", "190", "--resting-hr", "45"],
    [
        "analyze",
        "{file}",
        "--json",
        "--hr-zones",
        "115,135,155,172,188",
        "--sex",
        "female",
        "--max-hr",
        "190",
        "--resting-hr",
        "45",
    ],
    ["analyze", "{file}", "--power-zones", "150,200,250,300,350", "--ftp", "250"],
    ["parse", "{file}", "--json"],
    ["parse", "{file}", "--mode", "forensic"],
    ["parse", "{file}", "--strip-pii"],
    ["parse", "{file}", "--no-unknown"],
    ["inspect", "{file}"],
    ["inspect", "{file}", "--limit", "5"],
]
# Invocations with no file argument, run once.
GLOBAL_INVOCATIONS = [["codes"], ["nosuchcommand"], []]

RUNNER_JS = """
import { main } from "./cli.js";

const cases = JSON.parse(process.argv[2]);
const out = {};
for (const [key, argv] of cases) {
  const lines = [];
  const code = main(argv, (s) => lines.push(s), () => {});
  out[key] = { code, stdout: lines.length ? `${lines.join("\\n")}\\n` : "" };
}
process.stdout.write(JSON.stringify(out));
"""


def python_side(cases: list[tuple[str, list[str]]]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for key, argv in cases:
        argv = [a.replace(".SIDE.fit", ".py.fit") for a in argv]
        # A TextIOWrapper over BytesIO, because `parse --json` writes canonical bytes
        # to sys.stdout.buffer -- a StringIO has no .buffer and the capture would
        # crash on exactly the invocation that matters most.
        raw = io.BytesIO()
        buf = io.TextIOWrapper(raw, encoding="utf-8", newline="")
        err = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
                code = py_main(argv)
        except SystemExit as exc:
            code = int(exc.code or 0)
        buf.flush()
        out[key] = {"code": code, "stdout": raw.getvalue().decode("utf-8")}
    return out


def typescript_side(cases: list[tuple[str, list[str]]]) -> dict[str, dict]:
    js_dir = ROOT / "js"
    subprocess.run(["npm", "run", "build"], cwd=js_dir, check=True, capture_output=True)
    runner = js_dir / "dist" / "esm" / "_clirun.mjs"
    runner.write_text(RUNNER_JS, encoding="utf-8")
    payload = json.dumps([[k, [x.replace(".SIDE.fit", ".ts.fit") for x in a]] for k, a in cases])
    try:
        res = subprocess.run(
            ["node", str(runner), payload], cwd=js_dir, capture_output=True, text=True
        )
    finally:
        runner.unlink(missing_ok=True)
    if res.returncode != 0:
        raise SystemExit(f"running the TypeScript CLI failed:\n{res.stderr.strip()}")
    return json.loads(res.stdout)


def _tolerant_equal(a: object, b: object) -> bool:
    """Tree equality with last-ULP tolerance on floats.

    Used ONLY for `analyze --json`: the report's full-precision load fields pass
    through exp/pow, and CPython takes those from the *platform's* libm — its own
    output differs across OSes in the last ULP, so demanding that V8 byte-match one
    platform's libm is a phantom target (ADR-0009 §6 extension, F39). Canonical
    parse output contains no such field and stays byte-exact.
    """
    if isinstance(a, float) and isinstance(b, (int, float)):
        if a == b:
            return True
        scale = max(abs(a), abs(float(b)))
        return scale > 0 and abs(a - float(b)) / scale < 1e-12
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_tolerant_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_tolerant_equal(x, y) for x, y in zip(a, b, strict=True))
    return a == b


def first_difference(a: str, b: str) -> str:
    for i, (ca, cb) in enumerate(zip(a, b, strict=False)):
        if ca != cb:
            lo = max(0, i - 60)
            return (
                f"at char {i}:\n      python:     ...{a[lo : i + 60]!r}"
                f"\n      typescript: ...{b[lo : i + 60]!r}"
            )
    return f"one is a prefix of the other (python {len(a)}, typescript {len(b)})"


def main() -> None:
    corpus = ROOT / "corpus" / "cases"
    cases: list[tuple[str, list[str]]] = []
    outdir = pathlib.Path("/tmp/chiptime-cli-parity")
    outdir.mkdir(exist_ok=True)
    for path in sorted(corpus.glob("*/*/input.fit")):
        name = f"{path.parent.parent.name}/{path.parent.name}"
        slug = name.replace("/", "_")
        for inv in INVOCATIONS:
            # {out} resolves per side so the two runs cannot clobber each other;
            # the bytes are compared afterwards.
            argv = [
                a.replace("{file}", str(path)).replace("{out}", str(outdir / f"{slug}.SIDE.fit"))
                for a in inv
            ]
            cases.append((f"{name}::{' '.join(inv)}", argv))
    for inv in GLOBAL_INVOCATIONS:
        cases.append((f"<global>::{' '.join(inv) or '(no args)'}", list(inv)))

    py = python_side(cases)
    ts = typescript_side(cases)

    failures: list[tuple[str, str]] = []
    for key, _ in cases:
        p_res = py[key]
        t_res = ts.get(key)
        if t_res is None:
            failures.append((key, "missing from the TypeScript run"))
            continue
        if p_res["code"] != t_res["code"]:
            failures.append((key, f"exit code python={p_res['code']} typescript={t_res['code']}"))
            continue
        if p_res["stdout"] != t_res["stdout"]:
            # The repair stdout names the output path, which legitimately differs
            # (.py.fit vs .ts.fit); normalize before comparing.
            a = p_res["stdout"].replace(".py.fit", ".fit")
            b = t_res["stdout"].replace(".ts.fit", ".fit")
            if a != b:
                if "analyze" in key and "--json" in key:
                    try:
                        if _tolerant_equal(json.loads(a), json.loads(b)):
                            continue
                    except ValueError:
                        pass
                failures.append((key, first_difference(a, b)))
                continue
        if "repair" in key and p_res["code"] in (0, 2):
            slug = key.split("::")[0].replace("/", "_")
            base = pathlib.Path("/tmp/chiptime-cli-parity")
            pb = (base / f"{slug}.py.fit").read_bytes()
            tb = (base / f"{slug}.ts.fit").read_bytes()
            if pb != tb:
                failures.append(
                    (key, f"repaired FILE bytes differ: py {len(pb)}B vs ts {len(tb)}B")
                )

    if failures:
        print(f"cli parity: {len(failures)} of {len(cases)} invocation(s) diverged")
        for key, where in failures[:6]:
            print(f"\n  {key}\n    {where}")
        if len(failures) > 6:
            print(f"\n  ... and {len(failures) - 6} more")
        raise SystemExit(1)

    print(f"cli parity: ok -- {len(cases)} invocations, stdout and exit codes identical")


if __name__ == "__main__":
    main()
