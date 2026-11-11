import { describe, expect, it } from "vitest";
import { asciiName, fromBase64, readPresetFile, toBase64 } from "./presetfile";

function file(header: string, name: string, size = 1452): Uint8Array {
  const bytes = new Uint8Array(size);
  [...(header + name)].forEach((c, i) => (bytes[i] = c.charCodeAt(0)));
  return bytes;
}

describe("preset files", () => {
  it("reads the model and the name", () => {
    expect(readPresetFile(file("***DSP408V010***", "FSMXLmGDLsEq  "))).toEqual({
      model: "408",
      name: "FSMXLmGDLsEq",
    });
    expect(readPresetFile(file("***DSP206V010***", "Pas touch\xe9 svp"))).toEqual({
      model: "206",
      name: "Pas touché svp",
    });
  });

  it("refuses other files", () => {
    expect(readPresetFile(new TextEncoder().encode("hello"))).toMatch(/not a t.racks/);
    expect(readPresetFile(file("***FIR408V010***", "x"))).toMatch(/not a t.racks/);
    expect(readPresetFile(file("***DSP408V010***", "x", 20000))).toMatch(/too large/);
  });

  it("makes names the DSP accepts", () => {
    expect(asciiName("Pas touché svp")).toBe("Pas touche svp");
    expect(asciiName("Bühne → L")).toBe("Buhne ? L");
    expect(asciiName("A very long preset name")).toBe("A very long pr");
  });

  it("round-trips base64", () => {
    const bytes = Uint8Array.from([0, 1, 0x10, 0x03, 0xff, 0xe9]);
    expect(fromBase64(toBase64(bytes))).toEqual(bytes);
  });
});
