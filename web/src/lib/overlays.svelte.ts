// Channels whose response curves are overlaid on every channel's response graph. Shared by all
// the graphs and remembered in this browser.

const STORAGE_KEY = "dsp408.response.overlays";

function load(): string[] {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]") as unknown;
    return Array.isArray(saved) ? saved.filter((p): p is string => typeof p === "string") : [];
  } catch {
    return [];
  }
}

class Overlays {
  paths = $state<string[]>(load());

  toggle(path: string): void {
    this.paths = this.paths.includes(path)
      ? this.paths.filter((p) => p !== path)
      : [...this.paths, path];
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(this.paths));
    } catch {
      // not persisted: fine
    }
  }
}

export const overlays = new Overlays();
