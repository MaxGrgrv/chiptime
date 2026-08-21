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
export interface BaseTypeVector {
  type: string;
  byte: number;
  /** Decimal string, or "nan" — uint64's sentinel exceeds Number.MAX_SAFE_INTEGER. */
  value: string;
  expected: boolean;
}
export interface CrcVector {
  hex: string;
  seed?: number;
  crc: number;
}
export interface Utf8Vector {
  hex: string;
  /** What the decoder's string path produces: a string, an array of segments, or null. */
  value: string | string[] | null;
}
export interface TimestampVector {
  fit: number;
  iso: string;
  local: string;
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
export const baseTypeVectors = load<BaseTypeVector[]>("base-types.json");
export const crcVectors = load<CrcVector[]>("crc16.json");
export const utf8Vectors = load<Utf8Vector[]>("utf8.json");
export const timestampVectors = load<TimestampVector[]>("timestamps.json");

export function fromHex(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = Number.parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}
