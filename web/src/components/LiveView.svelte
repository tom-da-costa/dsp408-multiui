<script lang="ts">
  // "Live" tab: one strip per channel for running a show (meters, gain, mute, indicators).
  // The channels shown are picked in the top row and remembered in this browser.
  import { ChannelSelection } from "../lib/selection.svelte";
  import ChannelPicker from "./ChannelPicker.svelte";
  import LiveStrip from "./LiveStrip.svelte";

  const selection = new ChannelSelection("dsp408.live.hidden");
  const shown = $derived(selection.shown);
</script>

<div class="live">
  <ChannelPicker {selection} />

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
