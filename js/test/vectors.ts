import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const dir = fileURLToPath(new URL("./vectors/", import.meta.url));

function load<T>(name: string): T {
  return JSON.parse(readFileSync(`${dir}${name}`, "utf-8")) as T;
}

export interface OkVector {
  name: string;
  input: string;
  expected: string;
}
export interface RefuseVector {
  name: string;
  input: string;
  pythonError: string;
}
export interface AsymmetryVector {
  name: string;
  input: string;
  pythonOutput: string;
  note: string;
}
export interface NumericVectors {
  pyRound: [number, number][];
  pyRoundN: [number, number, number][];
  floorDiv: [number, number, number][];
  divmod: [number, number, [number, number]][];
}

export const canonicalOk = load<OkVector[]>("canonical-ok.json");
export const canonicalRefuse = load<RefuseVector[]>("canonical-refuse.json");
export const canonicalAsymmetry = load<AsymmetryVector[]>("canonical-asymmetry.json");
export const numericVectors = load<NumericVectors>("numeric.json");
