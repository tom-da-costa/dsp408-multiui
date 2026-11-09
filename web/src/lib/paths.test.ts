import { describe, expect, it } from "vitest";
import { getPath, setPath } from "./paths";
import { dbToPos, formatDb, meterPos, posToDb, quantizeGain } from "./scale";
import { throttleLatest } from "./throttle";

describe("paths", () => {
  it("gets and sets nested values", () => {
    const state = { outputs: [{ gain_db: 0, peq: [{ q: 1 }] }] };
    setPath(state, "outputs.0.gain_db", -6);
    setPath(state, "outputs.0.peq.0", { q: 2 });
    expect(getPath(state, "outputs.0.gain_db")).toBe(-6);
    expect(getPath(state, "outputs.0.peq.0.q")).toBe(2);
    expect(getPath(state, "outputs.5.gain_db")).toBeUndefined();
    expect(() => setPath(state, "nope.0.x", 1)).toThrow();
  });
});

describe("scale", () => {
  it("maps dB to fader position and back", () => {
    expect(dbToPos(-60)).toBe(0);
    expect(dbToPos(12)).toBe(1);
    expect(dbToPos(0)).toBeCloseTo(0.75);
    for (const db of [-55, -40, -20, -6, 0, 6]) expect(posToDb(dbToPos(db))).toBeCloseTo(db);
    expect(posToDb(-1)).toBe(-60);
    expect(posToDb(2)).toBe(12);
  });

  it("quantizes like the device", () => {
    expect(quantizeGain(-30.3)).toBe(-30.5);
    expect(quantizeGain(-3.24)).toBe(-3.2);
    expect(quantizeGain(99)).toBe(12);
  });

  it("formats", () => {
    expect(formatDb(3)).toBe("+3.0");
    expect(formatDb(-60)).toBe("-∞");
    expect(formatDb(null)).toBe("—");
    expect(meterPos(null, -90)).toBe(0);
    expect(meterPos(20, -90)).toBe(1); // full scale = +20 dB
    expect(meterPos(12, -90, 12)).toBe(1);
  });
});

describe("throttleLatest", () => {
  it("sends the first value at once and the latest one later", async () => {
    const sent: number[] = [];
    const t = throttleLatest((v: number) => sent.push(v), 20);
    t.push(1);
    t.push(2);
    t.push(3);
    expect(sent).toEqual([1]);
    await new Promise((resolve) => setTimeout(resolve, 40));
    expect(sent).toEqual([1, 3]);
    t.push(4);
    t.flush();
    expect(sent.at(-1)).toBe(4);
  });
});
