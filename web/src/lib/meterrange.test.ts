import { beforeEach, describe, expect, it, vi } from "vitest";

const store = new Map<string, string>();
vi.stubGlobal("localStorage", {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
  removeItem: (k: string) => void store.delete(k),
});

const { meterRange, meterTicks, segmentGaps, segmentLevel, segmentZoneStart } = await import(
  "./meterrange.svelte"
);

describe("meter range", () => {
  beforeEach(() => {
    store.clear();
    meterRange.reset();
    meterRange.setSegment(0);
  });

  it("defaults to -40 .. +20 dBu", () => {
    expect([meterRange.min, meterRange.max]).toEqual([-40, 20]);
    expect(meterRange.isDefault).toBe(true);
  });

  it("clamps each end to its own range and remembers it", () => {
    meterRange.setMin(-200);
    meterRange.setMax(-10);
    expect([meterRange.min, meterRange.max]).toEqual([-90, 0]);
    expect(JSON.parse(store.get("dsp408.meterRange") ?? "{}")).toEqual({ min: -90, max: 0, segment: 0 });
    meterRange.setMin(0);
    meterRange.setMax(99);
    expect([meterRange.min, meterRange.max]).toEqual([-20, 40]);
    expect(meterRange.isDefault).toBe(false);
  });

  it("keeps both ends on the 10 dB grid", () => {
    meterRange.setMin(-47);
    meterRange.setMax(14);
    expect([meterRange.min, meterRange.max]).toEqual([-50, 10]);
  });

  it("graduates every 10 dB inside the range", () => {
    expect(meterTicks(-60, 20)).toEqual([20, 10, 0, -10, -20, -30, -40, -50, -60]);
    expect(meterTicks(-45, 15)).toEqual([10, 0, -10, -20, -30, -40]);
  });

  it("remembers the segment size, continuous by default", () => {
    expect(meterRange.segment).toBe(0);
    meterRange.setSegment(5);
    expect(meterRange.segment).toBe(5);
    expect(JSON.parse(store.get("dsp408.meterRange") ?? "{}").segment).toBe(5);
    meterRange.setSegment(3); // not offered: ignored
    expect(meterRange.segment).toBe(5);
  });
});

describe("segments", () => {
  it("draws the level up to the top of the segment it reaches", () => {
    expect(segmentLevel(-13.2, -40, 5)).toBe(-10);
    expect(segmentLevel(-15, -40, 5)).toBe(-15); // exactly on an edge
    expect(segmentLevel(0.4, -40, 1)).toBe(1);
    expect(segmentLevel(-13.2, -40, 0)).toBe(-13.2); // continuous
  });

  it("starts each colour zone on a segment edge, a segment taking the colour of its top", () => {
    // zones: yellow above 0, orange above +6, red above +12
    expect([0, 6, 12].map((db) => segmentZoneStart(db, -40, 5))).toEqual([0, 5, 10]);
    expect([0, 6, 12].map((db) => segmentZoneStart(db, -40, 2))).toEqual([0, 6, 12]);
    expect([0, 6, 12].map((db) => segmentZoneStart(db, -40, 10))).toEqual([0, 0, 10]);
    expect(segmentZoneStart(6, -40, 0)).toBe(6);
  });

  it("draws gaps only when segmented", () => {
    expect(segmentGaps("to top", -40, 20, 0)).toBeNull();
    expect(segmentGaps("to top", -40, 20, 10)).toBe(
      "repeating-linear-gradient(to top, transparent 0 calc(16.6667% - 1px), " +
        "#0b0c0f calc(16.6667% - 1px) 16.6667%)",
    );
  });
});
