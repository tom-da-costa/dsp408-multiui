<script lang="ts">
  // Params › Gain: one strip per channel picked in the row above (meter, fader, mute, phase).
  import { app } from "../lib/app.svelte";
  import type { ChannelSelection } from "../lib/selection.svelte";
  import ChannelPicker from "./ChannelPicker.svelte";
  import Strip from "./Strip.svelte";

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
  <ChannelPicker {selection} />
  <div class="strips">
    {#each paths as path, i (path)}
      {@const [side, n] = path.split(".")}
      {@const index = Number(n)}
      {@const channel = side === "inputs" ? device.inputs[index] : device.outputs[index]}
      {#if channel}
        {#if i > 0 && side === "outputs" && paths[i - 1]?.startsWith("inputs.")}
          <div class="divider"></div>
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
{/if}

<style>
  .strips {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    overscroll-behavior-x: contain;
    padding-bottom: 6px;
    height: calc(100% - 46px);
    min-height: 380px;
  }
  .divider {
    flex: 0 0 2px;
    background: var(--line);
    border-radius: 1px;
  }
</style>
