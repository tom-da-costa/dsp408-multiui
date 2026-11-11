import { beforeEach, describe, expect, it, vi } from "vitest";

// A device with Out 1 + Out 5 linked, In A + In B linked; nav reads the URL hash at import.
const fake = vi.hoisted(() => {
  globalThis.location = { hash: "" } as Location;
  const channel = (index: number, name: string, linked: number[] = []) => ({ index, name, linked });
  return {
    app: {
      screenLocked: false,
      hello: { profile: { input_count: 4 } },
      device: {
        inputs: [channel(0, "Vox", [1]), channel(1, "Gtr", [0]), channel(2, "InC"), channel(3, "InD")],
        outputs: [
          channel(0, "SubL", [4]),
          channel(1, "SubR"),
          channel(2, "TopL"),
          channel(3, "TopR"),
          channel(4, "SubL2", [0]),
          channel(5, "Out6"),
          channel(6, "Out7"),
          channel(7, "Out8"),
        ],
      },
      meters: null as unknown,
    },
  };
});
vi.mock("./app.svelte", () => ({ app: fake.app }));

const { links } = await import("./links.svelte");
const { ChannelSelection } = await import("./selection.svelte");

describe("links, merging off", () => {
  beforeEach(() => links.setMerge(false));

  it("shows every channel on its own, linked ones marked", () => {
    expect(links.members("outputs.4")).toEqual(["outputs.4"]);
    expect(links.isShown("outputs.4")).toBe(true);
    expect(links.slot("outputs.4")).toBe("Out 5");
    expect(links.name("outputs.4")).toBe("SubL2");
    expect(links.mark("outputs.4")).toBe(" 🔗");
    expect(links.mark("outputs.1")).toBe("");
  });
});

describe("links, merging on", () => {
  beforeEach(() => links.setMerge(true));

  it("shows a link group as its lowest-numbered member", () => {
    expect(links.group("outputs.4")).toEqual(["outputs.0", "outputs.4"]);
    expect(links.lead("outputs.4")).toBe("outputs.0");
    expect(links.isShown("outputs.0")).toBe(true);
    expect(links.isShown("outputs.4")).toBe(false);
    expect(links.isShown("outputs.1")).toBe(true);
  });

  it("labels a merged group with every member", () => {
    expect(links.slot("outputs.0")).toBe("Out 1+5");
    expect(links.shortSlot("inputs.0")).toBe("A+B");
    expect(links.name("outputs.0")).toBe("SubL / SubL2");
    expect(links.mark("outputs.0")).toBe("");
  });

  it("meters the loudest member and lights an indicator if any member's is", () => {
    // levels: 4 inputs then 8 outputs
    fake.app.meters = {
      levels: [-20, -10, null, null, -30, -40, null, null, -5, null, null, null],
      clip: [false, true, false, false, false, false, false, false, false, false, false, false],
      comp: [false, false, false, false, true, false, false, false],
      limit: [false, false, false, false, false, false, false, false],
    };
    expect(links.meter("inputs.0")).toEqual({ level: -10, clip: true, comp: null, limit: null });
    expect(links.meter("outputs.0")).toEqual({ level: -5, clip: false, comp: true, limit: false });
    links.setMerge(false);
    expect(links.meter("outputs.0")).toEqual({ level: -30, clip: false, comp: false, limit: false });
  });

  it("lists, shows and hides a group as one entry of the channel picker", () => {
    const selection = new ChannelSelection("test.hidden");
    expect(selection.entries.map((c) => c.path)).not.toContain("outputs.4");
    expect(selection.shown).toContain("outputs.0");
    selection.toggle("outputs.0");
    expect(selection.hidden).toEqual(["outputs.0", "outputs.4"]);
    expect(selection.shown).not.toContain("outputs.0");
    selection.toggle("outputs.0");
    expect(selection.hidden).toEqual([]);
  });
});
