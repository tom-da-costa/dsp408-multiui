import { beforeEach, describe, expect, it, vi } from "vitest";

const store = new Map<string, string>();
vi.stubGlobal("localStorage", {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
  removeItem: (k: string) => void store.delete(k),
});

const { meterRange, meterTicks } = await import("./meterrange.svelte");

describe("meter range", () => {
  beforeEach(() => {
    store.clear();
    meterRange.reset();
  });

  it("defaults to -60 .. +20 dBu", () => {
    expect([meterRange.min, meterRange.max]).toEqual([-60, 20]);
    expect(meterRange.isDefault).toBe(true);
  });

  it("clamps each end to its own range and remembers it", () => {
    meterRange.setMin(-200);
    meterRange.setMax(-10);
    expect([meterRange.min, meterRange.max]).toEqual([-90, 0]);
    expect(JSON.parse(store.get("dsp408.meterRange") ?? "{}")).toEqual({ min: -90, max: 0 });
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
});
