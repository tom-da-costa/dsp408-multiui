import { describe, expect, it } from "vitest";
import {
  formatGeqFreq,
  formatHz,
  fromPos,
  gainStep,
  GEQ_FREQS,
  logIndexStep,
  logSnap,
  meterPos,
  meterFill,
  meterGradient,
  COMP_COLOR,
  LIMIT_COLOR,
  sampleStep,
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

describe("meterPos", () => {
  it("is linear in dB between the bottom and the top of the range, clamped", () => {
    expect(meterPos(null, -60, 20)).toBe(0);
    expect(meterPos(-90, -60, 20)).toBe(0);
    expect(meterPos(-20, -60, 20)).toBe(0.5);
    expect(meterPos(0, -60, 20)).toBe(0.75);
    expect(meterPos(30, -60, 20)).toBe(1);
    expect(meterPos(-40, -80, 0)).toBe(0.5);
  });
});

describe("device steps", () => {
  it("gain: 0.5 dB below -20 dB, 0.1 dB above", () => {
    expect(gainStep(0, 1)).toBe(0.1);
    expect(gainStep(-19.9, -1)).toBe(-20);
    expect(gainStep(-20, -1)).toBe(-20.5);
    expect(gainStep(-20.5, 1)).toBe(-20);
    expect(gainStep(12, 1)).toBe(12);
    expect(gainStep(-60, -1)).toBe(-60);
  });

  it("log index: one raw step, clamped", () => {
    const up = logIndexStep(1000, 19.7, 20160, 300, 1);
    expect(up / 1000).toBeCloseTo((20160 / 19.7) ** (1 / 300), 2);
    expect(logIndexStep(up, 19.7, 20160, 300, -1)).toBeCloseTo(1000, -1);
    expect(logIndexStep(20160, 19.7, 20160, 300, 1)).toBeCloseTo(20160);
    expect(logIndexStep(0.4, 0.4, 128, 100, -1)).toBeCloseTo(0.4);
  });

  it("delay: one sample at 96 kHz", () => {
    expect(sampleStep(0, 96000, 1)).toBeCloseTo(1 / 96, 6);
    expect(sampleStep(4.438, 96000, 1)).toBeCloseTo(427 / 96, 6);
    expect(sampleStep(0, 96000, -1)).toBe(0);
  });

  it("formats low frequencies with a decimal", () => {
    expect(formatHz(20.16)).toBe("20.2");
    expect(formatHz(440)).toBe("440");
    expect(formatHz(1234)).toBe("1.23k");
  });
});

describe("meter zones", () => {
  it("green to 0 dBu, yellow to +6, orange to +12, red above", () => {
    const css = meterGradient("to top", (db) => meterPos(db, -60, 20));
    expect(css).toBe(
      "linear-gradient(to top, #2bbf7f 0 75.00%, #ffd23f 75.00% 82.50%, " +
        "#ff8c1a 82.50% 90.00%, #ff4d5e 90.00% 100%)",
    );
  });

  it("fills with the limiter colour, then the compressor's, else the zones", () => {
    expect(meterFill("zones", false, false)).toBe("zones");
    expect(meterFill("zones", null, null)).toBe("zones");
    expect(meterFill("zones", false, true)).toBe(COMP_COLOR);
    expect(meterFill("zones", true, false)).toBe(LIMIT_COLOR);
    expect(meterFill("zones", true, true)).toBe(LIMIT_COLOR);
  });
});

describe("logSnap", () => {
  it("snaps to the nearest index of the log scale, clamped", () => {
    // 20 Hz .. 20 kHz in 300 steps: 1 kHz is index 170.0..., held exactly by a step
    const step = (i: number) => 20 * 1000 ** (i / 300);
    expect(logSnap(1000, 20, 20000, 300)).toBeCloseTo(step(Math.round(300 * Math.log(50) / Math.log(1000))), 9);
    expect(logSnap(step(42) * 1.001, 20, 20000, 300)).toBeCloseTo(step(42), 9);
    expect(logSnap(5, 20, 20000, 300)).toBe(20);
    expect(logSnap(50000, 20, 20000, 300)).toBeCloseTo(20000, 9);
  });
});
