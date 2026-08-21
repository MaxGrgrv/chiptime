#!/usr/bin/env node
/**
 * Finish the dual ESM/CJS build.
 *
 * `tsc` cannot rename its output, so the CommonJS pass emits `.js` files that Node
 * would otherwise read as ESM (the package is `"type": "module"`). A per-directory
 * package.json flips the interpretation for that subtree — the standard shim, and
 * the fiddly part the F31 critique flagged.
 */
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const cjs = fileURLToPath(new URL("../dist/cjs/package.json", import.meta.url));
writeFileSync(cjs, `${JSON.stringify({ type: "commonjs" }, null, 2)}\n`);
console.log("build: wrote dist/cjs/package.json ({ type: commonjs })");
