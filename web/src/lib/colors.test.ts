import { describe, expect, it } from "vitest";
import { channelColor } from "./colors";

describe("channelColor", () => {
  it("gives each channel of a side its own colour", () => {
    const outputs = Array.from({ length: 8 }, (_, i) => channelColor(`outputs.${i}`));
    expect(new Set(outputs).size).toBe(8);
    const inputs = Array.from({ length: 4 }, (_, i) => channelColor(`inputs.${i}`));
    expect(new Set(inputs).size).toBe(4);
  });

  it("gives a link group the colour of its lowest-numbered channel", () => {
    expect(channelColor("outputs.5", [2, 7])).toBe(channelColor("outputs.2"));
    expect(channelColor("outputs.2", [5, 7])).toBe(channelColor("outputs.2"));
    expect(channelColor("inputs.1", [0])).toBe(channelColor("inputs.0"));
  });
});
