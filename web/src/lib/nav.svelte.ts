// Navigation: the selected tab and the open channel detail, mirrored in the URL hash so the
// browser's back button (or a phone's back gesture) closes the detail.

export const TABS = [
  ["mixer", "Mixer", "🎚"],
  ["matrix", "Matrix", "▦"],
  ["presets", "Presets", "☰"],
  ["settings", "Settings", "⚙"],
] as const;
export type Tab = (typeof TABS)[number][0];

const CHANNEL = /^(inputs|outputs)\.(\d+)$/;

export function isChannelPath(text: string): boolean {
  return CHANNEL.test(text);
}

/** Label of a channel slot: "In A" for inputs.0, "Out 3" for outputs.2. */
export function slotLabel(path: string): string {
  const match = CHANNEL.exec(path);
  if (!match) return path;
  const n = Number(match[2]);
  return match[1] === "inputs" ? `In ${String.fromCharCode(65 + n)}` : `Out ${n + 1}`;
}

class Nav {
  tab = $state<Tab>("mixer");
  /** Path of the channel whose detail is open ("outputs.3"), or null. */
  detail = $state<string | null>(null);
  /** Open/closed state of the detail sections, kept while switching channels. */
  sections = $state<Record<string, boolean>>({});

  constructor() {
    this.fromHash();
  }

  fromHash(): void {
    const hash = location.hash.slice(1);
    if (isChannelPath(hash)) {
      this.tab = "mixer";
      this.detail = hash;
    } else {
      this.detail = null;
      this.tab = (TABS.find(([key]) => key === hash)?.[0] ?? this.tab) as Tab;
    }
  }

  select(tab: Tab): void {
    this.tab = tab;
    this.detail = null;
    history.replaceState(null, "", `#${tab}`);
  }

  open(path: string): void {
    // Push a history entry for the first detail, so "back" returns to the mixer.
    if (this.detail === null) history.pushState({ detail: true }, "", `#${path}`);
    else history.replaceState(history.state, "", `#${path}`);
    this.detail = path;
  }

  close(): void {
    if (this.detail === null) return;
    if ((history.state as { detail?: boolean } | null)?.detail) {
      history.back(); // the popstate listener calls fromHash()
    } else {
      // Opened from a link or a reload: there is no entry of ours to go back to.
      this.detail = null;
      history.replaceState(null, "", `#${this.tab}`);
    }
  }

  isOpen(id: string, fallback = true): boolean {
    return this.sections[id] ?? fallback;
  }

  toggle(id: string, fallback = true): void {
    this.sections[id] = !this.isOpen(id, fallback);
  }
}

export const nav = new Nav();
