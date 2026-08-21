#!/usr/bin/env node
/**
 * Zero-dependency source guards for js/src (F31 Req 20, ADR-0009 §3).
 *
 * A lint plugin could express these, at the cost of a dependency and a config
 * dialect. A grep says the same thing to a human reading CI output.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src/", import.meta.url));

const RULES = [
  {
    pattern: /\bMath\.round\s*\(/,
    exempt: ["numeric.ts"],
    message:
      "Math.round is half-up; Python's round() is half-to-even. Use pyRound/pyRoundN from numeric.ts.",
  },
  {
    // ADR-0009 §5. The real rule is "never on an output path", which is not
    // greppable, so this is a blanket ban with an exemption list. Date.toISOString()
    // always emits milliseconds where Python's strftime does not, so a Date that
    // reaches output puts a wrong timestamp in canonical JSON. Use civilFromUnix and
    // the integer formatters in decode.ts.
    pattern: /\bnew Date\b|\bDate\.(now|parse|UTC)\s*\(/,
    exempt: [],
    message:
      "Date is banned in js/src (ADR-0009 §5): toISOString() always emits milliseconds, " +
      "which the Python formatter does not. Use civilFromUnix/fitTsToIso.",
  },
];

function* walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) yield* walk(full);
    else if (entry.endsWith(".ts")) yield full;
  }
}

let failures = 0;
for (const file of walk(SRC)) {
  const rel = relative(SRC, file);
  const lines = readFileSync(file, "utf-8").split("\n");
  for (const rule of RULES) {
    if (rule.exempt.includes(rel)) continue;
    lines.forEach((line, i) => {
      // Prose in a comment naming the banned call is fine; a call site is not.
      if (line.trimStart().startsWith("*") || line.trimStart().startsWith("//")) return;
      if (rule.pattern.test(line)) {
        console.error(`src/${rel}:${i + 1}: ${rule.message}\n    ${line.trim()}`);
        failures++;
      }
    });
  }
}

if (failures > 0) {
  console.error(`\n${failures} guard violation(s).`);
  process.exit(1);
}
console.log("guards: ok");
