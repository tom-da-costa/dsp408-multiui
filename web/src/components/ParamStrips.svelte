<script lang="ts">
  // A setting of the Params tab (delay, filters, dynamics) as one strip per channel, like the
  // mixer: the fields stand up as vertical sliders (lib/layout.ts).
  import { app } from "../lib/app.svelte";
  import { setStripLayout } from "../lib/layout";
  import { nav, SIDES, slotLabel, type Param } from "../lib/nav.svelte";
  import ChipBar from "./ChipBar.svelte";
  import ParamBlock from "./ParamBlock.svelte";

  interface Props {
    param: Param;
    /** Channels to show, in order. */
    paths: string[];
    /** Show the all / inputs / outputs row (settings that exist on both sides). */
    sides?: boolean;
  }

  let { param, paths, sides = false }: Props = $props();

  setStripLayout();

  function channelOf(path: string) {
    const [side, n] = path.split(".");
    return (side === "inputs" ? app.device?.inputs : app.device?.outputs)?.[Number(n)];
  }
</script>

<div class="view">
{#if sides}
  <ChipBar
    items={SIDES.map(([key, label]) => ({ key, label }))}
    selected={nav.side}
    onselect={(k) => (nav.side = k as typeof nav.side)}
    label="Channels shown"
  />
{/if}

<div class="strips">
  {#each paths as path, i (path)}
    {@const channel = channelOf(path)}
    {#if channel}
      {#if i > 0 && path.startsWith("outputs.") && paths[i - 1]?.startsWith("inputs.")}
        <div class="divider"></div>
      {/if}
      <section class="strip" class:muted={channel.mute} style:--ch={app.color(path)}>
        <button class="name" onclick={() => nav.open(path)} title="Open this channel">
          <span class="slot">{slotLabel(path)}{channel.linked.length ? " 🔗" : ""}</span>
          <strong>{channel.name || "—"}</strong>
        </button>
        <ParamBlock {param} {path} />
      </section>
    {/if}
  {:else}
    <p class="muted">No channel to show.</p>
  {/each}
</div>
</div>

<style>
  /* The page minus the setting row above: the strips take all the height, like the mixer's. */
  .view {
    height: calc(100% - 46px);
    min-height: 460px;
    display: flex;
    flex-direction: column;
  }
  .strips {
    flex: 1;
    min-height: 0;
    display: flex;
    align-items: stretch;
    gap: 6px;
    overflow-x: auto;
    overscroll-behavior-x: contain;
    padding-bottom: 6px;
  }
  .divider {
    flex: 0 0 2px;
    background: var(--line);
    border-radius: 1px;
  }
  .strip {
    flex: 0 0 auto;
    min-width: 150px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 8px 6px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius);
  }
  .strip.muted {
    /* Muted: red diagonal hatching, as in the mixer. */
    background-image: repeating-linear-gradient(
      -45deg,
      rgb(255 77 94 / 0.3) 0 4px, /* --danger at 30 % */
      transparent 4px 16px
    );
  }
  .name {
    border: 2px solid var(--ch);
    color: var(--ch);
    display: grid;
    min-height: 40px;
    padding: 2px 6px;
    line-height: 1.15;
    text-align: center;
  }
  .name span,
  .name strong {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .slot {
    font-size: 0.7rem;
  }
  p {
    font-size: 0.85rem;
    text-align: center;
  }
</style>
