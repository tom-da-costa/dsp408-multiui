import { beforeEach, describe, expect, it, vi } from "vitest";

// A minimal localStorage (node has none).
const store = new Map<string, string>();
vi.stubGlobal("localStorage", {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
  removeItem: (k: string) => void store.delete(k),
});

const { hasSignal, signal, SIGNAL_DEFAULT_DB } = await import("./signal.svelte");

describe("SIG indicator", () => {
  beforeEach(() => {
    store.clear();
    signal.setThreshold(SIGNAL_DEFAULT_DB);
  });

  it("lights strictly above the threshold, never without data", () => {
    expect(hasSignal(-59.9, -60)).toBe(true);
    expect(hasSignal(-60, -60)).toBe(false);
    expect(hasSignal(-86, -60)).toBe(false); // an unconnected input
    expect(hasSignal(null, -60)).toBe(false);
  });

  it("defaults to -60 dBu", () => {
    expect(signal.threshold).toBe(-60);
  });

  it("clamps, rounds and remembers the threshold", () => {
    signal.setThreshold(-45.4);
    expect(signal.threshold).toBe(-45);
    expect(store.get("dsp408.signalThreshold")).toBe("-45");
    signal.setThreshold(-200);
    expect(signal.threshold).toBe(-80);
    signal.setThreshold(10);
    expect(signal.threshold).toBe(-20);
  });
});
