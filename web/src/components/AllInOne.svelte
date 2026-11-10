<script lang="ts">
  // "All-in-one" tab: one column per channel with the settings picked in the chip row.
  // The choice is remembered in this browser.
  import { app } from "../lib/app.svelte";
  import { nav, PARAM_SCOPE, PARAMS, SIDES, slotLabel, type Param } from "../lib/nav.svelte";
  import ChipBar from "./ChipBar.svelte";
  import LevelBar from "./LevelBar.svelte";
  import ParamBlock from "./ParamBlock.svelte";

  const STORAGE_KEY = "dsp408.aio.params";
  const DEFAULT: Param[] = ["gain", "delay", "filters", "comp", "limit", "gate", "matrix"];

  function load(): Param[] {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null") as unknown;
      if (Array.isArray(saved)) return PARAMS.map(([k]) => k).filter((k) => saved.includes(k));
    } catch {
      // storage unavailable or corrupt: use the default
    }
    return DEFAULT;
  }

  let shown = $state<Param[]>(load());

  function toggle(key: string) {
    const param = key as Param;
    // Keep the PARAMS order whatever the click order.
    shown = PARAMS.map(([k]) => k).filter((k) => (k === param ? !shown.includes(k) : shown.includes(k)));
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(shown));
    } catch {
      // not persisted: fine
    }
  }

  const device = $derived(app.device);
  const channels = $derived(
    [
      ...(device?.inputs ?? []).map((c, i) => ({ path: `inputs.${i}`, channel: c })),
      ...(device?.outputs ?? []).map((c, i) => ({ path: `outputs.${i}`, channel: c })),
    ].filter(({ path }) => nav.side === "all" || path.startsWith(nav.side)),
  );

  function applies(param: Param, path: string): boolean {
    const scope = PARAM_SCOPE[param];
    return scope === "all" || path.startsWith(scope);
  }
</script>

<ChipBar
  items={PARAMS.filter(([key]) => key !== "link").map(([key, label]) => ({ key, label }))}
  selected={shown}
  onselect={toggle}
  label="Settings shown"
/>
<ChipBar
  items={SIDES.map(([key, label]) => ({ key, label }))}
  selected={nav.side}
  onselect={(k) => (nav.side = k as typeof nav.side)}
  label="Channels shown"
/>

<div class="strips">
  {#each channels as { path, channel } (path)}
    <section class="strip" class:muted={channel.mute} style:--ch={app.color(path)}>
      <button class="head" onclick={() => nav.open(path)} title="Open this channel">
        <span class="slot">{slotLabel(path)}{channel.linked.length ? " 🔗" : ""}</span>
        <strong>{channel.name || "—"}</strong>
      </button>
      <LevelBar {path} compact />
      {#each shown.filter((p) => applies(p, path)) as param (param)}
        <ParamBlock {param} {path} />
      {/each}
    </section>
  {/each}
  {#if shown.length === 0}
    <p class="muted">Pick the settings to show above.</p>
  {/if}
</div>

<style>
  .strips {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    overflow-x: auto;
    overscroll-behavior-x: contain;
    scroll-snap-type: x proximity;
    padding-bottom: 8px;
  }
  .strip {
    flex: 0 0 min(300px, calc(100vw - 110px));
    scroll-snap-align: start;
    display: grid;
    gap: 8px;
    padding: 8px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-top: 3px solid var(--ch);
    border-radius: var(--radius);
  }
  .strip :global(section.card) {
    margin: 0;
    background: var(--panel-2);
  }
  .head {
    display: grid;
    justify-items: start;
    min-height: 40px;
    padding: 2px 8px;
    line-height: 1.15;
    text-align: left;
    background: none;
  }
  .slot {
    font-size: 0.75rem;
    color: var(--muted);
  }
  .strip.muted strong {
    color: var(--danger);
  }
</style>
