<script lang="ts">
  // "Live" tab: one strip per channel for running a show (meters, gain, mute, indicators).
  import { app } from "../lib/app.svelte";
  import { nav, SIDES } from "../lib/nav.svelte";
  import ChipBar from "./ChipBar.svelte";
  import LiveStrip from "./LiveStrip.svelte";

  const paths = $derived(
    [
      ...(app.device?.inputs ?? []).map((_, i) => `inputs.${i}`),
      ...(app.device?.outputs ?? []).map((_, i) => `outputs.${i}`),
    ].filter((p) => nav.side === "all" || p.startsWith(nav.side)),
  );
</script>

<div class="live">
  <ChipBar
    items={SIDES.map(([key, label]) => ({ key, label }))}
    selected={nav.side}
    onselect={(k) => (nav.side = k as typeof nav.side)}
    label="Channels shown"
  />
  <div class="strips">
    {#each paths as path, i (path)}
      {#if i > 0 && path.startsWith("outputs.") && paths[i - 1]?.startsWith("inputs.")}
        <div class="divider"></div>
      {/if}
      <LiveStrip {path} />
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
