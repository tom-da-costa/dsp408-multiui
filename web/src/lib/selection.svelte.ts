// Channels shown by a multi-channel view (Live, All-in-one), picked with ChannelPicker and
// remembered in this browser. The hidden channels are stored, not the shown ones, so
// everything is shown by default. With "Merge linked channels", a link group is one entry (its
// lead): toggling it shows or hides every member.

import { app } from "./app.svelte";
import { links } from "./links.svelte";

type Prefix = "" | "inputs." | "outputs.";

function load(key: string): string[] {
  try {
    const saved = JSON.parse(localStorage.getItem(key) ?? "[]") as unknown;
    return Array.isArray(saved) ? saved.filter((p): p is string => typeof p === "string") : [];
  } catch {
    return [];
  }
}

export class ChannelSelection {
  hidden = $state<string[]>([]);

  constructor(private readonly storageKey: string) {
    this.hidden = load(storageKey);
  }

  /** Every channel of the device, inputs first. */
  get all(): { path: string; name: string }[] {
    return [
      ...(app.device?.inputs ?? []).map((c, i) => ({ path: `inputs.${i}`, name: c.name })),
      ...(app.device?.outputs ?? []).map((c, i) => ({ path: `outputs.${i}`, name: c.name })),
    ];
  }

  /** The entries of the picker: every channel, or one per link group when merging. */
  get entries(): { path: string; name: string }[] {
    return this.all.filter((c) => links.isShown(c.path));
  }

  get shown(): string[] {
    return this.entries.filter((c) => !this.hidden.includes(c.path)).map((c) => c.path);
  }

  isShown(path: string): boolean {
    return !this.hidden.includes(path);
  }

  /** Show or hide `path`, with the members merged into it. */
  toggle(path: string): void {
    const members = links.members(path);
    const others = this.hidden.filter((p) => !members.includes(p));
    this.save(this.hidden.includes(path) ? others : [...others, ...members]);
  }

  /** Show every channel starting with `prefix` ("" = all), leaving the others as they are. */
  showAll(prefix: Prefix): void {
    this.save(this.hidden.filter((p) => !p.startsWith(prefix)));
  }

  /** Show only the channels starting with `prefix` ("" = all of them). */
  only(prefix: Prefix): void {
    this.save(this.all.filter((c) => !c.path.startsWith(prefix)).map((c) => c.path));
  }

  /** Exactly the channels starting with `prefix` are shown. */
  isOnly(prefix: Prefix): boolean {
    const shown = this.shown;
    return (
      shown.length > 0 &&
      shown.every((p) => p.startsWith(prefix)) &&
      this.entries.filter((c) => c.path.startsWith(prefix)).every((c) => this.isShown(c.path))
    );
  }

  private save(next: string[]): void {
    if (app.screenLocked) return; // the locked screen keeps the channels shown
    this.hidden = next;
    try {
      localStorage.setItem(this.storageKey, JSON.stringify(next));
    } catch {
      // not persisted: fine
    }
  }
}
