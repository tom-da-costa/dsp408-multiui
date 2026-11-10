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

/** A distinct colour per channel, stable whatever the selection; none of them is the green,
 * blue or orange already used for the channel's own curves. */
const COLORS = [
  "#f783ac", "#91a7ff", "#ffd8a8", "#d0bfff", // In A-D
  "#ff6b6b", "#e599f7", "#66d9e8", "#c0eb75", "#ffe066", "#ffffff", "#fcc2d7", "#b2f2bb", // Out 1-8
]; // prettier-ignore

export function overlayColor(path: string, inputCount = 4): string {
  const [side, n] = path.split(".");
  const index = (side === "outputs" ? inputCount : 0) + Number(n);
  return COLORS[index % COLORS.length]!;
}
