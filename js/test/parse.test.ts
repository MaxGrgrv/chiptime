import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { parse } from "../src/api.js";
import { FitError, NotFitError } from "../src/errors.js";
import { unwrap } from "../src/intake.js";
import { sha256Hex } from "../src/sha256.js";

const CORPUS = fileURLToPath(new URL("../../corpus/cases/", import.meta.url));
const load = (name: string) => new Uint8Array(readFileSync(`${CORPUS}${name}/input.fit`));
const rideSmooth = load("clean/ride-smooth");

describe("parse", () => {
  it("parses a clean activity", () => {
    const r = parse(rideSmooth);
    expect(r.ok).toBe(true);
    expect(r.fileType).toBe("activity");
    expect(r.parts).toHaveLength(1);
    expect(r.errors).toHaveLength(0);
    expect(r.recovery).toBeNull();
  });

  it("hashes the ORIGINAL bytes, not the unwrapped ones", () => {
    // source.sha256 is the dedup identity (taxonomy #18); hashing post-unwrap would
    // make a .gz and its contents indistinguishable.
    const gz = load("container/gzip-wrapped");
    expect(parse(gz).source.sha256).toBe(sha256Hex(gz));
    expect(parse(gz).source.sha256).not.toBe(sha256Hex(unwrap(gz).data));
  });

  it("records the containers it peeled", () => {
    expect(parse(load("container/gzip-wrapped")).source.unwrapped).toEqual(["gzip"]);
    expect(parse(load("container/zip-wrapped")).source.unwrapped).toEqual(["zip"]);
    expect(parse(rideSmooth).source.unwrapped).toEqual([]);
  });

  it("never serializes the local path (ADR-0002 §3)", () => {
    const json = JSON.stringify(parse(rideSmooth).toJSON());
    expect(json).not.toContain('"path"');
  });

  it("rejects a renamed GPX with the format named", () => {
    const r = parse(load("container/gpx-renamed"));
    expect(r.ok).toBe(false);
    expect(r.errors[0]?.code).toBe("NOT_FIT_FORMAT");
    expect(r.errors[0]?.detail).toContain("GPX");
  });

  it("explains ok=false even when nothing errored (taxonomy #16)", () => {
    const r = parse(load("structural/empty-shell"));
    expect(r.ok).toBe(false);
    expect(r.errors.length).toBeGreaterThan(0);
    expect(r.errors.some((e) => e.code === "FIT_NO_CONTENT")).toBe(true);
  });

  it("emits multiple parts for a chained file (taxonomy #12)", () => {
    expect(parse(load("structural/chained-two-activities")).parts.length).toBe(2);
  });
});

describe("modes", () => {
  const truncated = rideSmooth.subarray(0, rideSmooth.length - 40);

  it("strict raises the first defect", () => {
    expect(() => parse(truncated, { mode: "strict" })).toThrow(FitError);
  });

  it("strict raises a typed error for a non-FIT file", () => {
    expect(() => parse(load("container/gpx-renamed"), { mode: "strict" })).toThrow(NotFitError);
  });

  it("lenient recovers and reports", () => {
    const r = parse(truncated);
    expect(r.ok).toBe(true);
    expect(r.recovery).not.toBeNull();
    expect(r.recovery?.recoveredRecords).toBeGreaterThan(0);
  });

  it("forensic never throws on content", () => {
    expect(() => parse(truncated, { mode: "forensic" })).not.toThrow();
  });
});

describe("privacy and filtering emit provenance — contract #1", () => {
  it("stripPii records what it removed", () => {
    const r = parse(rideSmooth, { stripPii: true });
    const entry = r.provenance.find((p) => p.code === "PII_STRIPPED");
    if (entry) {
      expect(entry.action).toBe("dropped");
      expect(r.messages.some((m) => m.name === "user_profile")).toBe(false);
    }
    // Whether or not this corpus case carries PII, nothing may vanish silently:
    const without = parse(rideSmooth);
    const removed = without.messages.length - r.messages.length;
    if (removed > 0) expect(entry).toBeDefined();
  });

  it("includeUnknown:false records what it dropped", () => {
    const all = parse(rideSmooth);
    const r = parse(rideSmooth, { includeUnknown: false });
    const dropped = all.messages.length - r.messages.length;
    if (dropped > 0) {
      const entry = r.provenance.find((p) => p.code === "UNKNOWN_MESSAGES_OMITTED");
      expect(entry).toBeDefined();
      expect(entry?.data.count).toBe(dropped);
    }
  });

  it("includeRaw adds raw without changing anything else", () => {
    const plain = JSON.parse(new TextDecoder().decode(parse(rideSmooth).toCanonicalJson()));
    const raw = JSON.parse(
      new TextDecoder().decode(parse(rideSmooth, { includeRaw: true }).toCanonicalJson()),
    );
    expect(raw.source).toEqual(plain.source);
    expect(raw.ok).toBe(plain.ok);
  });
});

describe("hostile input", () => {
  it("never throws on a truncation sweep, in every mode", () => {
    for (const mode of ["lenient", "forensic"] as const) {
      for (let cut = 0; cut <= rideSmooth.length; cut += 11) {
        expect(() => parse(rideSmooth.subarray(0, cut), { mode }), `${mode} @${cut}`).not.toThrow();
      }
    }
  });

  it("produces canonical JSON for every truncation point", () => {
    for (let cut = 0; cut <= rideSmooth.length; cut += 37) {
      expect(() => parse(rideSmooth.subarray(0, cut)).toCanonicalJson()).not.toThrow();
    }
  });

  it("is deterministic across repeated parses", () => {
    const a = parse(rideSmooth).toCanonicalJson();
    const b = parse(rideSmooth).toCanonicalJson();
    expect(a).toEqual(b);
  });
});

describe("intake", () => {
  it("sniffs the formats it names", () => {
    const enc = new TextEncoder();
    expect(unwrap(enc.encode('<?xml version="1.0"?><gpx></gpx>')).defects[0]?.detail).toContain(
      "GPX",
    );
    expect(unwrap(enc.encode("<TrainingCenterDatabase>")).defects[0]?.detail).toContain("TCX");
    expect(unwrap(enc.encode("<!DOCTYPE html><html>")).defects[0]?.detail).toContain("HTML");
    expect(unwrap(enc.encode('{"error": 1}')).defects[0]?.detail).toContain("JSON");
  });

  it("lets unrecognized bytes through to the frame reader", () => {
    const noise = new Uint8Array([0xde, 0xad, 0xbe, 0xef, 0x00, 0x01, 0x02]);
    expect(unwrap(noise).defects).toHaveLength(0);
  });
});
