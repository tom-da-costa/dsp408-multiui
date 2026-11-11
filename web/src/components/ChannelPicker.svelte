<script lang="ts">
  // The row that picks the channels a multi-channel view shows (Live, All-in-one, Params):
  // shortcuts all / inputs / outputs, then one toggle per channel. With `side`, only that side's
  // channels are listed (a setting that exists on inputs or outputs only).
  import { app } from "../lib/app.svelte";
  import { links } from "../lib/links.svelte";
  import type { ChannelSelection } from "../lib/selection.svelte";

  interface Props {
    selection: ChannelSelection;
    side?: "inputs" | "outputs";
  }

  let { selection, side }: Props = $props();

  const prefix = $derived(side ? (`${side}.` as const) : "");
  const all = $derived(selection.entries.filter((c) => c.path.startsWith(prefix)));
  const allShown = $derived(all.every((c) => selection.isShown(c.path)));
  const locked = $derived(app.screenLocked); // the locked screen keeps the channels shown
</script>

<div class="picker" role="group" aria-label="Channels shown">
  <button class="quick" class:on={allShown} disabled={locked} onclick={() => selection.showAll(prefix)}
    >All</button
  >
  {#if !side}
    <button
      class="quick"
      class:on={!allShown && selection.isOnly("inputs.")}
      disabled={locked}
      onclick={() => selection.only("inputs.")}>In</button
    >
    <button
      class="quick"
      class:on={!allShown && selection.isOnly("outputs.")}
      disabled={locked}
      onclick={() => selection.only("outputs.")}>Out</button
    >
  {/if}
  <span class="sep"></span>
  {#each all as c (c.path)}
    <button
      class="chan ch-bar"
      style:--ch={app.color(c.path)}
      class:on={selection.isShown(c.path)}
      aria-pressed={selection.isShown(c.path)}
      disabled={locked}
      title={`${links.slot(c.path)} ${links.name(c.path)}`}
      onclick={() => selection.toggle(c.path)}
    >
      <span>{links.shortSlot(c.path)}</span>
      <small>{links.name(c.path)}</small>
    </button>
  {/each}
</div>

<style>
  .picker {
    flex: none;
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
  .picker .chan:not(.on) {
    border-color: color-mix(in srgb, var(--ch) 60%, var(--line));
  }
  .picker .chan:not(.on) span,
  .picker .chan:not(.on) small {
    color: var(--ch);
  }
  .picker .on:disabled {
    opacity: 1;
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
</style>
