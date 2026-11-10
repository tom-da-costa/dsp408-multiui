import { describe, expect, it } from "vitest";
import { channelResponse, lowPassMagnitude, parseSlope, peqBandDb } from "./response";
import type { Channel } from "./types";

const db = (m: number) => 20 * Math.log10(m);
const SLOPES = ["Off", "BW-6", "BL-6", "BW-12", "BL-12", "LR-12", "BW-18", "BL-18", "BW-24", "BL-24",
  "LR-24", "BW-30", "BL-30", "BW-36", "BL-36", "LR-36", "BW-42", "BL-42", "BW-48", "BL-48", "LR-48"]; // prettier-ignore
const TYPES = ["Peak", "Low Shelf", "High Shelf", "LP -6dB", "LP -12dB", "HP -6dB", "HP -12dB",
  "Allpass 1", "Allpass 2"]; // prettier-ignore

describe("crossover slopes", () => {
  it("cut-off levels: Butterworth and Bessel -3 dB, Linkwitz-Riley -6 dB", () => {
    for (const name of SLOPES.slice(1)) {
      const slope = parseSlope(name)!;
      const expected = slope.family === "LR" ? -6.02 : -3.01;
      expect(db(lowPassMagnitude(slope, 1)), name).toBeCloseTo(expected, 1);
    }
    expect(parseSlope("Off")).toBeNull();
  });

  it("asymptotic slope in dB per octave", () => {
    for (const name of ["BW-6", "BW-24", "LR-24", "LR-48", "BW-48"]) {
      const slope = parseSlope(name)!;
      const perOctave = db(lowPassMagnitude(slope, 200)) - db(lowPassMagnitude(slope, 100));
      expect(perOctave, name).toBeCloseTo(-slope.dbPerOctave, 0);
    }
  });

  it("passband is flat", () => {
    expect(db(lowPassMagnitude(parseSlope("BL-24")!, 0.01))).toBeCloseTo(0, 2);
  });
});

describe("PEQ bands", () => {
  const band = { gain_db: 6, freq_hz: 1000, q: 1.41, type: 0, bypass: false };
  it("peak: full gain at the centre, flat far away", () => {
    expect(peqBandDb(band, "Peak", 1000)).toBeCloseTo(6, 6);
    expect(peqBandDb(band, "Peak", 20)).toBeCloseTo(0, 1);
    expect(peqBandDb({ ...band, gain_db: -9 }, "Peak", 1000)).toBeCloseTo(-9, 6);
  });
  it("shelves reach the gain on their side and half of it at f0", () => {
    expect(peqBandDb(band, "Low Shelf", 20)).toBeCloseTo(6, 1);
    expect(peqBandDb(band, "Low Shelf", 20000)).toBeCloseTo(0, 1);
    expect(peqBandDb(band, "Low Shelf", 1000)).toBeCloseTo(3, 1);
    expect(peqBandDb(band, "High Shelf", 20000)).toBeCloseTo(6, 1);
  });
  it("pass filters, all-pass and bypass", () => {
    expect(peqBandDb(band, "LP -6dB", 1000)).toBeCloseTo(-3.01, 2);
    expect(peqBandDb({ ...band, q: Math.SQRT1_2 }, "HP -12dB", 1000)).toBeCloseTo(-3.01, 2);
    expect(peqBandDb(band, "Allpass 2", 1000)).toBe(0);
    expect(peqBandDb({ ...band, bypass: true }, "Peak", 1000)).toBe(0);
  });
});

describe("channel response", () => {
  const channel: Channel & { geq: number[] } = {
    index: 4,
    name: "Sub",
    gain_db: 0,
    mute: false,
    phase: false,
    delay_ms: 0,
    linked: [],
    peq_bypass: false,
    peq: [
      { gain_db: 4, freq_hz: 50, q: 2, type: 0, bypass: false },
      { gain_db: 0, freq_hz: 500, q: 2, type: 0, bypass: false }, // neutral: not drawn
      { gain_db: -6, freq_hz: 80, q: 2, type: 0, bypass: true }, // off
    ],
    crossover: {
      hpf: { freq_hz: 30, slope: 10, enabled: true }, // LR-24
      lpf: { freq_hz: 100, slope: 10, enabled: true },
    },
    geq: Array(31).fill(0),
  };

  it("sums crossover and active bands", () => {
    const r = channelResponse(channel, TYPES, SLOPES, [30, 50, 100, 1000]);
    expect(r.peq.map((p) => p.band)).toEqual([0]);
    expect(r.geq).toBeNull();
    expect(r.crossover[0]).toBeCloseTo(-6.0, 0); // LR-24 HPF at its cut-off (LPF adds a little)
    expect(r.total[1]).toBeGreaterThan(2); // the +4 dB peak at 50 Hz
    expect(r.total[3]).toBeLessThan(-60); // far above the 100 Hz low-pass
  });

  it("PEQ bypass and GEQ", () => {
    const geq = Array(31).fill(0);
    geq[17] = 6; // 1 kHz
    const r = channelResponse({ ...channel, peq_bypass: true, geq }, TYPES, SLOPES, [1000]);
    expect(r.peq).toEqual([]);
    expect(r.geq![0]).toBeCloseTo(6, 1);
  });
});
