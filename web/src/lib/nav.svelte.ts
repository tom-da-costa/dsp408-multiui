// Navigation: main tab plus the sub-tab of "Params" (a setting) and "Channels" (a channel),
// mirrored in the URL hash (#params/gain, #channels/outputs.3, #aio …) so that reloads and the
// browser's back button (or a phone's back gesture) work. The screen lock freezes it.

import { app } from "./app.svelte";

export const TABS = [
  ["live", "Live", "🎛"],
  ["params", "Params", "🎚"],
  ["channels", "Channels", "🔈"],
  ["aio", "All-in-one", "▥"],
  ["limiter", "Limiter calc", "🧮"],
  ["presets", "Presets", "☰"],
  ["settings", "Settings", "⚙"],
] as const;
export type Tab = (typeof TABS)[number][0];

/** The settings, as sub-tabs of "Params" and as the blocks of the all-in-one view. */
export const PARAMS = [
  ["gain", "Gain"],
  ["delay", "Delay"],
  ["eq", "EQ"],
  ["filters", "Filters"],
  ["comp", "Comp"],
  ["limit", "Limit"],
  ["gate", "Gate"],
  ["geq", "GEQ"],
  ["matrix", "Matrix"],
  ["link", "Link"],
] as const;
export type Param = (typeof PARAMS)[number][0];

/** Which channels a setting exists on. */
export const PARAM_SCOPE: Record<Param, "all" | "inputs" | "outputs"> = {
  gain: "all",
  delay: "all",
  eq: "all",
  filters: "all",
  comp: "outputs",
  limit: "outputs",
  gate: "inputs",
  geq: "inputs",
  matrix: "outputs",
  link: "all",
};

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

function isParam(text: string): text is Param {
  return PARAMS.some(([key]) => key === text);
}

function isTab(text: string): text is Tab {
  return TABS.some(([key]) => key === text);
}

class Nav {
  tab = $state<Tab>("live");
  param = $state<Param>("gain");
  channel = $state("inputs.0");
  /** Open/closed state of collapsible sections, by section id. */
  sections = $state<Record<string, boolean>>({});

  constructor() {
    this.fromHash();
  }

  get hash(): string {
    if (this.tab === "params") return `params/${this.param}`;
    if (this.tab === "channels") return `channels/${this.channel}`;
    return this.tab;
  }

  /** Locked screen: the view stays as it is (tabs, sub-tabs, channel shown). */
  private get frozen(): boolean {
    return app.screenLocked;
  }

  fromHash(): void {
    if (this.frozen) {
      this.go(false); // back / forward while locked: put the current view's URL back
      return;
    }
    const [head = "", sub = ""] = location.hash.slice(1).split("/");
    if (isTab(head)) {
      this.tab = head;
      if (head === "params" && isParam(sub)) this.param = sub;
      if (head === "channels" && isChannelPath(sub)) this.channel = sub;
    } else if (isChannelPath(head)) {
      this.tab = "channels"; // links of the previous UI (#outputs.3)
      this.channel = head;
    } else if (head === "mixer" || head === "matrix") {
      this.tab = "params";
      this.param = head === "mixer" ? "gain" : "matrix";
    }
  }

  private go(push: boolean): void {
    const url = `#${this.hash}`;
    if (url === location.hash) return;
    if (push) history.pushState({ nav: true }, "", url);
    else history.replaceState(history.state, "", url);
  }

  select(tab: Tab): void {
    if (this.frozen) return;
    this.tab = tab;
    this.go(false);
  }

  selectParam(param: Param): void {
    if (this.frozen) return;
    this.tab = "params";
    this.param = param;
    this.go(false);
  }

  selectChannel(path: string): void {
    if (this.frozen) return;
    this.tab = "channels";
    this.channel = path;
    this.go(false);
  }

  /** Jump to a channel from another view; "back" returns to that view. */
  open(path: string): void {
    if (this.frozen) return;
    this.tab = "channels";
    this.channel = path;
    this.go(true);
  }

  isOpen(id: string, fallback = true): boolean {
    return this.sections[id] ?? fallback;
  }

  toggle(id: string, fallback = true): void {
    this.sections[id] = !this.isOpen(id, fallback);
  }
}

export const nav = new Nav();
