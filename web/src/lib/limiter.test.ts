import { describe, expect, it } from "vitest";
import { computeLimiter, inputDbu, type LimiterInput, validate } from "./limiter";

const HORNPLANS_EXAMPLE: LimiterInput = {
  // the calculator's default: 2 x 800 W AES 8 ohm speakers on one channel of a 2000 W / 4 ohm amp
  speakerAesW: 1600,
  impedanceOhm: 4,
  ampGainDb: 32,
  ampPowerW: 2000,
  load: "open",
  mode: "hard",
};

// The owner's check (Hornplans and another calculator agree): 1700 W AES, 8 ohm, 40.5 dB.
const OWNER: LimiterInput = {
  speakerAesW: 1700,
  impedanceOhm: 8,
  ampGainDb: 40.5,
  ampPowerW: null,
  load: "open",
  mode: "hard",
};

describe("limiter calculator", () => {
  it("hard = the Hornplans calculator (dBu mode)", () => {
    const r = computeLimiter(HORNPLANS_EXAMPLE);
    expect(r.speakerDbu).toBeCloseTo(6.34, 2); // √(1600/1.5625·4) = 64 V
    expect(r.ampDbu).toBeCloseTo(6.23, 2); // √(2000/2·4) = 63.2 V
    expect(r.limitedBy).toBe("amp");
    expect(r.hornplansDbu).toBe(6.2);
    expect(r.thresholdDbu).toBe(6.2);
    expect(r.compThresholdDbu).toBe(6); // the DSP's 0.5 dB step, rounded down
    expect(r.limitThresholdDbu).toBe(12);
  });

  it("matches the owner's reference values", () => {
    const hardOpen = computeLimiter(OWNER);
    const hardClosed = computeLimiter({ ...OWNER, load: "closed" });
    const softOpen = computeLimiter({ ...OWNER, mode: "soft" });
    expect(hardOpen.thresholdDbu).toBe(1.1);
    expect(hardClosed.thresholdDbu).toBe(-0.7);
    expect(softOpen.thresholdDbu).toBe(3.1);
    expect(softOpen.hornplansDbu).toBe(1.1);
    // applied to the compressor, in 0.5 dB steps
    expect([hardOpen, hardClosed, softOpen].map((r) => r.compThresholdDbu)).toEqual([1, -1, 3]);
    expect(softOpen.limitThresholdDbu).toBe(9);
    // the amplifier (4000 W at 8 ohm: +3.7 dBu) does not limit here
    const withAmp = computeLimiter({ ...OWNER, ampPowerW: 4000 });
    expect(withAmp.ampDbu).toBeCloseTo(3.76, 2);
    expect(withAmp.limitedBy).toBe("speaker");
    expect(withAmp.thresholdDbu).toBe(1.1);
  });

  it("the amplifier stays a ceiling in soft mode", () => {
    // 3000 W at 8 ohm: amp limit +2.5 dBu, between hard (+1.1) and soft (+3.1)
    const hard = computeLimiter({ ...OWNER, ampPowerW: 3000 });
    const soft = computeLimiter({ ...OWNER, mode: "soft", ampPowerW: 3000 });
    expect(hard.limitedBy).toBe("speaker");
    expect(hard.thresholdDbu).toBe(1.1);
    expect(soft.limitedBy).toBe("amp");
    expect(soft.thresholdDbu).toBeCloseTo(Math.floor((soft.ampDbu ?? 0) * 10) / 10, 9);
    expect(soft.thresholdDbu).toBeLessThan(3.1);
  });

  it("closed load is 1.76 dB more conservative", () => {
    const open = computeLimiter(OWNER);
    const closed = computeLimiter({ ...OWNER, load: "closed" });
    expect(open.speakerDbu - closed.speakerDbu).toBeCloseTo(10 * Math.log10(1.5), 3);
  });

  it("rounds negative values down too, and clamps to the DSP range", () => {
    const low = computeLimiter({ ...OWNER, speakerAesW: 100, ampGainDb: 38 });
    expect(low.thresholdDbu).toBeLessThanOrEqual(low.speakerDbu);
    expect(Number.isInteger(low.compThresholdDbu * 2)).toBe(true);
    const hot = computeLimiter({ ...OWNER, ampGainDb: 0 });
    expect(hot.compThresholdDbu).toBe(20);
    expect(hot.limitThresholdDbu).toBe(20);
    expect(hot.clamped).toBe(true);
  });

  it("rounds to the DSP step down by default, or up on request", () => {
    // OWNER: hard open 1.1 dBu -> 1.0 down, 1.5 up; the limiter stays 6 dB above
    const down = computeLimiter(OWNER);
    expect(down.rounding).toBe("down");
    expect(down.compThresholdDbu).toBe(1);
    const up = computeLimiter({ ...OWNER, rounding: "up" });
    expect(up.compThresholdDbu).toBe(1.5);
    expect(up.limitThresholdDbu).toBe(7.5);
    // closed: -0.7 -> -1.0 down, -0.5 up
    expect(computeLimiter({ ...OWNER, load: "closed" }).compThresholdDbu).toBe(-1);
    expect(computeLimiter({ ...OWNER, load: "closed", rounding: "up" }).compThresholdDbu).toBe(-0.5);
  });

  it("leaves a value already on the 0.5 dB step as it is, whichever the rounding", () => {
    // the gain that puts the hard open threshold exactly on 1.0 dBu
    const exact = { ...OWNER, ampGainDb: 40.5 + computeLimiter(OWNER).speakerDbu - 1 };
    expect(computeLimiter(exact).thresholdDbu).toBe(1);
    expect(computeLimiter(exact).compThresholdDbu).toBe(1);
    expect(computeLimiter({ ...exact, rounding: "up" }).compThresholdDbu).toBe(1);
  });

  it("validates", () => {
    expect(validate(HORNPLANS_EXAMPLE)).toBeNull();
    expect(validate({ ...HORNPLANS_EXAMPLE, impedanceOhm: 0 })).toMatch(/Impedance/);
    expect(validate({ ...HORNPLANS_EXAMPLE, ampPowerW: -1 })).toMatch(/Amplifier power/);
    expect(inputDbu(0.775 ** 2, 1, 0)).toBeCloseTo(0, 9); // 0.775 V = 0 dBu
  });
});
