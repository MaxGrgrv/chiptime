#!/usr/bin/env node
/**
 * Contract #2, the cross-process half: canonical bytes must not depend on the
 * process that produced them.
 *
 * The vitest suite compares each vector against CPython's recorded output inside one
 * process. This hashes every vector's output and is invoked twice from separate
 * processes by CI, which is the invariant the Python side gets from its
 * `cross-os-determinism` job. It also prints the hash of CPython's recorded bytes, so
 * a cross-language mismatch is visible in the CI log rather than inferred.
 */
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
// Reads the built output, not the source: this checks what ships.
// Requires `npm run build` first (the CI job builds before invoking it).
const { dumps } = await import(new URL("../dist/esm/canonical.js", import.meta.url).href);

const vectorsPath = fileURLToPath(new URL("../test/vectors/canonical-ok.json", import.meta.url));
const vectors = JSON.parse(readFileSync(vectorsPath, "utf-8"));

const ours = createHash("sha256");
const cpython = createHash("sha256");
for (const v of vectors) {
  ours.update(dumps(JSON.parse(v.input)));
  cpython.update(Buffer.from(v.expected, "utf-8"));
}
const a = ours.digest("hex");
const b = cpython.digest("hex");
console.log(`typescript: ${a}`);
console.log(`cpython:    ${b}`);
if (a !== b) {
  console.error("determinism: cross-language hash mismatch");
  process.exit(1);
}
