<script lang="ts">
  // "Live" tab: one strip per channel for running a show (meters, gain, mute, indicators).
  // The channels shown are picked in the top row (shortcuts: all / inputs / outputs) and
  // remembered in this browser.
  import { app } from "../lib/app.svelte";
  import { slotLabel } from "../lib/nav.svelte";
  import LiveStrip from "./LiveStrip.svelte";

  const STORAGE_KEY = "dsp408.live.hidden";

  function load(): string[] {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]") as unknown;
      return Array.isArray(saved) ? saved.filter((p): p is string => typeof p === "string") : [];
    } catch {
      return [];
    }
  }

  // Hidden channels are stored (not the shown ones), so everything is shown by default.
  let hidden = $state<string[]>(load());

  function save(next: string[]) {
    hidden = next;
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // not persisted: fine
    }
  }

  const all = $derived([
    ...(app.device?.inputs ?? []).map((c, i) => ({ path: `inputs.${i}`, name: c.name })),
    ...(app.device?.outputs ?? []).map((c, i) => ({ path: `outputs.${i}`, name: c.name })),
  ]);
  const shown = $derived(all.filter((c) => !hidden.includes(c.path)).map((c) => c.path));

  function toggle(path: string) {
    save(hidden.includes(path) ? hidden.filter((p) => p !== path) : [...hidden, path]);
  }

  function only(prefix: "" | "inputs." | "outputs.") {
    save(all.filter((c) => !c.path.startsWith(prefix)).map((c) => c.path));
  }

  const isOnly = (prefix: string) =>
    shown.length > 0 &&
    shown.every((p) => p.startsWith(prefix)) &&
    all.filter((c) => c.path.startsWith(prefix)).every((c) => !hidden.includes(c.path));
</script>

<div class="live">
  <div class="picker" role="group" aria-label="Channels shown">
    <button class="quick" class:on={hidden.length === 0} onclick={() => only("")}>All</button>
    <button class="quick" class:on={isOnly("inputs.") && hidden.length > 0} onclick={() => only("inputs.")}
      >In</button
    >
    <button class="quick" class:on={isOnly("outputs.") && hidden.length > 0} onclick={() => only("outputs.")}
      >Out</button
    >
    <span class="sep"></span>
    {#each all as c (c.path)}
      <button
        class="chan"
        class:on={!hidden.includes(c.path)}
        aria-pressed={!hidden.includes(c.path)}
        title={`${slotLabel(c.path)} ${c.name}`}
        onclick={() => toggle(c.path)}
      >
        <span>{slotLabel(c.path).replace("In ", "").replace("Out ", "")}</span>
        <small>{c.name || "—"}</small>
      </button>
    {/each}
  </div>

  <div class="strips">
    {#each shown as path, i (path)}
      {#if i > 0 && path.startsWith("outputs.") && shown[i - 1]?.startsWith("inputs.")}
        <div class="divider"></div>
      {/if}
      <LiveStrip {path} />
    {:else}
      <p class="muted">No channel selected: pick some above.</p>
    {/each}
  </div>
</div>

<style>
  .live {
    height: 100%;
    display: flex;
    flex-direction: column;
    min-height: 420px;
  }
  .picker {
    display: flex;
    align-items: center;
    gap: 4px;
    overflow-x: auto;
    overscroll-behavior-x: contain;
    scrollbar-width: none;
    padding-bottom: 8px;
  }
  .picker::-webkit-scrollbar {
    display: none;
  }
  .picker button {
    flex: 0 0 auto;
    min-height: 38px;
    padding: 0 8px;
    border-radius: 8px;
    line-height: 1.05;
  }
  .quick {
    font-weight: 600;
    font-size: 0.85rem;
  }
  .chan {
    display: grid;
    justify-items: center;
    min-width: 42px;
    color: var(--muted);
  }
  .chan span {
    font-weight: 700;
    font-size: 0.85rem;
  }
  .chan small {
    max-width: 7ch;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: 0.65rem;
  }
  .picker .on {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--accent-text);
  }
  .sep {
    flex: 0 0 1px;
    align-self: stretch;
    margin: 4px 4px;
    background: var(--line);
  }
  .strips {
    flex: 1;
    display: flex;
    gap: 6px;
    overflow-x: auto;
    overscroll-behavior-x: contain;
    padding-bottom: 6px;
    min-height: 0;
  }
  .divider {
    flex: 0 0 2px;
    background: var(--line);
    border-radius: 1px;
  }
</style>
