// Settings shown as strips, one per channel, like the mixer (Params tab): the numeric fields
// become columns with a vertical slider (Field.svelte) and the sections drop their card
// (Section.svelte). Set for a whole subtree through a context.

import { getContext, setContext } from "svelte";

const STRIP = Symbol("strip-layout");

export function setStripLayout(on = true): void {
  setContext(STRIP, on);
}

export function inStrip(): boolean {
  return getContext<boolean | undefined>(STRIP) ?? false;
}
