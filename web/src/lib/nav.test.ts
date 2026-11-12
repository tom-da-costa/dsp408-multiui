import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./app.svelte", () => ({ app: { screenLocked: false } }));

const replaced: string[] = [];
vi.stubGlobal("history", {
  state: null,
  replaceState: (_s: unknown, _t: string, url: string) => {
    replaced.push(url);
    location.hash = url;
  },
  pushState: (_s: unknown, _t: string, url: string) => (location.hash = url),
});
vi.stubGlobal("location", { hash: "" });

/** A fresh `nav`, as built when the page loads with `hash`. */
async function load(hash: string) {
  location.hash = hash;
  vi.resetModules();
  return (await import("./nav.svelte")).nav;
}

describe("navigation", () => {
  beforeEach(() => {
    replaced.length = 0;
  });

  it("Link and Matrix are tabs of their own", async () => {
    expect((await load("#link")).tab).toBe("link");
    expect((await load("#matrix")).tab).toBe("matrix");
  });

  it("sends their old Params addresses to the new tabs", async () => {
    expect((await load("#params/link")).tab).toBe("link");
    expect(replaced).toEqual(["#link"]);
    expect((await load("#params/matrix")).tab).toBe("matrix");
    expect(replaced.at(-1)).toBe("#matrix");
  });

  it("Params no longer has Link and Matrix sub-tabs", async () => {
    const { PARAM_TABS } = await import("./nav.svelte");
    expect(PARAM_TABS.map(([key]) => key)).not.toContain("link");
    expect(PARAM_TABS.map(([key]) => key)).not.toContain("matrix");
    const nav = await load("#params/comp");
    expect([nav.tab, nav.param]).toEqual(["params", "comp"]);
  });
});
