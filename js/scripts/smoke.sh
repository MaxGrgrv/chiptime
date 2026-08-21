#!/usr/bin/env bash
# Pack the package, install the tarball into a clean directory, and import it from
# both Node ESM and Node CJS (F31 Req 23). Mirrors the Python `package-smoke` CI job.
#
# This tests the packaging surface — the exports map, the CJS type shim, the files
# allowlist — which is cheapest to debug while there is one module in it.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cd "$here"
npm run build >/dev/null
tarball="$(npm pack --silent --pack-destination "$work")"

cd "$work"
npm init -y >/dev/null 2>&1
npm install --silent --no-audit --no-fund "./$tarball" >/dev/null

cat > esm.mjs <<'JS'
import { iterFrames } from "chiptime";
import { CanonicalizationError, dumps } from "chiptime/canonical";
const bytes = dumps({ b: 1, a: [0, null, 2.5] });
if (!(bytes instanceof Uint8Array)) throw new Error("dumps did not return bytes");
const text = new TextDecoder().decode(bytes);
if (text !== '{"a":[0,null,2.5],"b":1}') throw new Error("ESM: canonical output wrong");
if (typeof CanonicalizationError !== "function") throw new Error("ESM: missing export");
if (typeof iterFrames !== "function") throw new Error("ESM: missing iterFrames");
if ([...iterFrames(new Uint8Array(0))].length !== 0) throw new Error("ESM: empty input should yield nothing");
console.log("esm ok");
JS

cat > cjs.cjs <<'JS'
const { iterFrames } = require("chiptime");
const { dumps, CanonicalizationError } = require("chiptime/canonical");
const text = new TextDecoder().decode(dumps({ b: 1, a: [0, null, 2.5] }));
if (text !== '{"a":[0,null,2.5],"b":1}') throw new Error("CJS: canonical output wrong");
if (typeof CanonicalizationError !== "function") throw new Error("CJS: missing export");
if (typeof iterFrames !== "function") throw new Error("CJS: missing iterFrames");
console.log("cjs ok");
JS

node esm.mjs
node cjs.cjs

# The package must not reach for an environment it may not have.
if grep -rn 'require("node:\|from "node:' "$work/node_modules/chiptime/dist"; then
  echo "smoke: dist reaches for a node: builtin — the browser build would break" >&2
  exit 1
fi
echo "smoke: ok (esm + cjs, no node: imports)"
