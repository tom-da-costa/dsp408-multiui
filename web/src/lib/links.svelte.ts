// "Merge linked channels" display option (Settings), remembered in this browser. When it is on,
// every view except Params › Matrix and Params › Link shows a link group as one channel: the
// group's lowest-numbered member (its "lead") stands for the group. A write to the lead reaches
// every member (the DSP applies it to the group), except the name and the routing, which views
// keep per member. Meters show the loudest member, and an indicator is lit if any member's is.

import { app } from "./app.svelte";
import { slotLabel } from "./nav.svelte";
import type { Channel } from "./types";

const STORAGE_KEY = "dsp408.mergeLinked";

function load(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function channelAt(path: string): Channel | undefined {
  const [side, n] = path.split(".");
  return (side === "outputs" ? app.device?.outputs : app.device?.inputs)?.[Number(n)];
}

export interface GroupMeter {
  level: number | null;
  clip: boolean;
  /** Null on inputs, or when the meters do not report it. */
  comp: boolean | null;
  limit: boolean | null;
}

class Links {
  merge = $state(load());

  setMerge(on: boolean): void {
    this.merge = on;
    try {
      localStorage.setItem(STORAGE_KEY, on ? "1" : "0");
    } catch {
      // not persisted: fine
    }
  }

  /** Every member of the link group of `path`, lowest-numbered first (`path` alone if unlinked). */
  group(path: string): string[] {
    const [side, n] = path.split(".");
    const indexes = [Number(n), ...(channelAt(path)?.linked ?? [])].sort((a, b) => a - b);
    return indexes.map((i) => `${side}.${i}`);
  }

  /** Channels shown as `path`: its whole group when merging, else `path` alone. */
  members(path: string): string[] {
    return this.merge ? this.group(path) : [path];
  }

  /** The channel that shows `path`: its group's lead when merging, else `path` itself. */
  lead(path: string): string {
    return this.members(path)[0] ?? path;
  }

  /** False for a member hidden in its lead's channel (merging on). */
  isShown(path: string): boolean {
    return this.lead(path) === path;
  }

  /** Slot label: "Out 1", or "Out 1+5" for a merged group. */
  slot(path: string): string {
    const [first, ...rest] = this.members(path).map(slotLabel);
    return [first ?? slotLabel(path), ...rest.map((s) => s.replace(/^(In|Out) /, ""))].join("+");
  }

  /** Short slot label for chips: "1", "A+B". */
  shortSlot(path: string): string {
    return this.slot(path).replace(/^(In|Out) /, "");
  }

  /** Channel name, or the members' names ("SubL / SubR") for a merged group. */
  name(path: string): string {
    return this.members(path)
      .map((p) => channelAt(p)?.name || "—")
      .join(" / ");
  }

  /** " 🔗" when `path` is linked but shown on its own (merging off). */
  mark(path: string): string {
    return !this.merge && (channelAt(path)?.linked.length ?? 0) > 0 ? " 🔗" : "";
  }

  /** Live meter of `path`, merged over its group when merging. */
  meter(path: string): GroupMeter {
    const meters = app.meters;
    const inputCount = app.hello?.profile.input_count ?? 4;
    const isOutput = path.startsWith("outputs.");
    let level: number | null = null;
    let clip = false;
    let comp: boolean | null = isOutput && meters?.comp ? false : null;
    let limit: boolean | null = isOutput && meters?.limit ? false : null;
    for (const p of this.members(path)) {
      const index = Number(p.split(".")[1]);
      const meterIndex = isOutput ? inputCount + index : index;
      const value = meters?.levels?.[meterIndex] ?? null;
      if (value !== null && (level === null || value > level)) level = value;
      clip ||= meters?.clip?.[meterIndex] ?? false;
      if (comp !== null) comp ||= meters?.comp?.[index] ?? false;
      if (limit !== null) limit ||= meters?.limit?.[index] ?? false;
    }
    return { level, clip, comp, limit };
  }
}

export const links = new Links();
