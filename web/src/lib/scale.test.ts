import { describe, expect, it } from "vitest";
import {
  formatGeqFreq,
  fromPos,
  GEQ_FREQS,
  meterDbToPos,
  parseNumber,
  snap,
  toPos,
} from "./scale";

describe("slider scales", () => {
  it.each(["lin", "log", "sqrt"] as const)("%s round-trips", (scale) => {
    for (const value of [1, 20, 440, 1000, 19000]) {
      expect(fromPos(toPos(value, 1, 20000, scale), 1, 20000, scale)).toBeCloseTo(value, 6);
    }
  });

  it("clamps positions", () => {
    expect(toPos(-5, 0, 10)).toBe(0);
    expect(toPos(50, 0, 10)).toBe(1);
    expect(toPos(10, 19.7, 20160, "log")).toBe(0);
    expect(fromPos(2, 0, 10)).toBe(10);
  });

  it("log puts 1 kHz near the middle of the audio range", () => {
    expect(toPos(1000, 19.7, 20160, "log")).toBeCloseTo(0.566, 2);
  });

  it("sqrt gives fine resolution near zero", () => {
    expect(fromPos(0.1, 0, 680, "sqrt")).toBeCloseTo(6.8, 6);
  });
});

describe("snap", () => {
  it("clamps and rounds to the resolution", () => {
    expect(snap(3.14159, -12, 12, 0.1)).toBe(3.1);
    expect(snap(-20.26, -90, 20, 0.5)).toBe(-20.5);
    expect(snap(99, -12, 12, 0.1)).toBe(12);
    expect(snap(1234.567, 19.7, 20160)).toBe(1234.567);
  });
});

describe("parseNumber", () => {
  it("accepts commas, signs and a k suffix", () => {
    expect(parseNumber("-3,5")).toBe(-3.5);
    expect(parseNumber("1.5k")).toBe(1500);
    expect(parseNumber(" 2K ")).toBe(2000);
    expect(parseNumber(".5")).toBe(0.5);
  });

  it("rejects junk", () => {
    expect(parseNumber("")).toBeNull();
    expect(parseNumber("abc")).toBeNull();
    expect(parseNumber("1.2.3")).toBeNull();
  });
});

describe("GEQ", () => {
  it("has 31 ISO bands", () => {
    expect(GEQ_FREQS).toHaveLength(31);
    expect(formatGeqFreq(1250)).toBe("1.25k");
    expect(formatGeqFreq(31.5)).toBe("31.5");
  });
});

describe("meterDbToPos", () => {
  it("spans -60 dB to full scale (+20 dB) and is monotonic", () => {
    expect(meterDbToPos(-90)).toBe(0);
    expect(meterDbToPos(0)).toBeCloseTo(0.7);
    expect(meterDbToPos(20)).toBe(1);
    expect(meterDbToPos(30)).toBe(1);
    let last = -1;
    for (let db = -60; db <= 20; db += 0.5) {
      const pos = meterDbToPos(db);
      expect(pos).toBeGreaterThan(last);
      last = pos;
    }
  });
});
