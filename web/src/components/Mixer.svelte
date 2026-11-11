<script lang="ts">
  // Params › Gain: one strip per channel picked in the row above (meter, fader, mute, phase).
  import { app } from "../lib/app.svelte";
  import type { ChannelSelection } from "../lib/selection.svelte";
  import ChannelPicker from "./ChannelPicker.svelte";
  import Strip from "./Strip.svelte";
  import SideDivider from "./SideDivider.svelte";

  interface Props {
    /** The Params tab's channel choice. */
    selection: ChannelSelection;
    /** Channels to show, in order. */
    paths: string[];
  }

  let { selection, paths }: Props = $props();

  const device = $derived(app.device);
  const inputCount = $derived(app.hello?.profile.input_count ?? 4);
</script>

{#if device}
<div class="view">
  <ChannelPicker {selection} />
  <div class="strips">
    {#each paths as path, i (path)}
      {@const [side, n] = path.split(".")}
      {@const index = Number(n)}
      {@const channel = side === "inputs" ? device.inputs[index] : device.outputs[index]}
      {#if channel}
        {#if i > 0 && side === "outputs" && paths[i - 1]?.startsWith("inputs.")}
          <SideDivider />
        {/if}
        <Strip
          {channel}
          {path}
          meterIndex={side === "inputs" ? index : inputCount + index}
          outputIndex={side === "inputs" ? null : index}
        />
      {/if}
    {:else}
      <p class="muted">No channel selected: pick some above.</p>
    {/each}
  </div>
</div>
{/if}

<style>
  /* The page minus the setting row above (as in ParamStrips). Below the minimum height (the
     picker and a strip with its fader at its minimum height), the page scrolls. */
  .view {
    height: calc(100% - 46px);
    min-height: 484px;
    display: flex;
    flex-direction: column;
  }
  .strips {
    flex: 1;
    min-height: 0;
    display: flex;
    gap: 6px;
    overflow-x: auto;
    overscroll-behavior-x: contain;
    padding-bottom: 6px;
  }
</style>
