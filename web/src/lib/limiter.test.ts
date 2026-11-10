import { describe, expect, it } from "vitest";
import { computeLimiter, inputDbu, type LimiterInput, validate } from "./limiter";

const HORNPLANS_EXAMPLE: LimiterInput = {
  // the calculator's default: 2 x 800 W AES 8 ohm speakers on one channel of a 2000 W / 4 ohm amp
  speakerAesW: 1600,
  impedanceOhm: 4,
  ampGainDb: 32,
  ampPowerW: 2000,
  load: "open",
  mode: "soft",
};

describe("limiter calculator", () => {
  it("reproduces the Hornplans calculator (dBu mode)", () => {
    const r = computeLimiter(HORNPLANS_EXAMPLE);
    expect(r.speakerDbu).toBeCloseTo(6.34, 2); // √(1600/1.5625·4) = 64 V
    expect(r.ampDbu).toBeCloseTo(6.23, 2); // √(2000/2·4) = 63.2 V
    expect(r.limitedBy).toBe("amp");
    expect(r.hornplansDbu).toBe(6.2);
    expect(r.compThresholdDbu).toBe(6); // soft: no margin, 0.5 dB step rounded down
    expect(r.limitThresholdDbu).toBe(12);
  });

  it("closed load is 1.76 dB more conservative; hard mode takes 2 dB off", () => {
    const open = computeLimiter({ ...HORNPLANS_EXAMPLE, ampPowerW: null });
    const closed = computeLimiter({ ...HORNPLANS_EXAMPLE, ampPowerW: null, load: "closed" });
    expect(open.speakerDbu - closed.speakerDbu).toBeCloseTo(10 * Math.log10(1.5), 3);
    expect(closed.hornplansDbu).toBe(4.5); // 4.578 rounded down
    const hard = computeLimiter({ ...HORNPLANS_EXAMPLE, ampPowerW: null, load: "closed", mode: "hard" });
    expect(hard.compThresholdDbu).toBe(2.5);
    expect(hard.limitThresholdDbu).toBe(8.5);
    expect(hard.limitedBy).toBe("speaker");
  });

  it("rounds negative values down too, and clamps to the DSP range", () => {
    const low = computeLimiter({ ...HORNPLANS_EXAMPLE, ampPowerW: null, speakerAesW: 100, ampGainDb: 38 });
    expect(low.hornplansDbu).toBeLessThanOrEqual(low.speakerDbu);
    expect(Number.isInteger(low.compThresholdDbu * 2)).toBe(true);
    const hot = computeLimiter({ ...HORNPLANS_EXAMPLE, ampPowerW: null, ampGainDb: 0 });
    expect(hot.compThresholdDbu).toBe(20);
    expect(hot.limitThresholdDbu).toBe(20);
    expect(hot.clamped).toBe(true);
  });

  it("validates", () => {
    expect(validate(HORNPLANS_EXAMPLE)).toBeNull();
    expect(validate({ ...HORNPLANS_EXAMPLE, impedanceOhm: 0 })).toMatch(/Impedance/);
    expect(validate({ ...HORNPLANS_EXAMPLE, ampPowerW: -1 })).toMatch(/Amplifier power/);
    expect(inputDbu(0.775 ** 2, 1, 0)).toBeCloseTo(0, 9); // 0.775 V = 0 dBu
  });
});
