<script lang="ts">
  import { app } from "../lib/app.svelte";
  import { nav, SIDES } from "../lib/nav.svelte";
  import ChipBar from "./ChipBar.svelte";
  import Strip from "./Strip.svelte";

  const device = $derived(app.device);
  const inputCount = $derived(app.hello?.profile.input_count ?? 4);
</script>

{#if device}
  <ChipBar
    items={SIDES.map(([key, label]) => ({ key, label }))}
    selected={nav.side}
    onselect={(k) => (nav.side = k as typeof nav.side)}
    label="Channels shown"
  />
  <div class="strips">
    {#if nav.side !== "outputs"}
      {#each device.inputs as channel, i (channel.index)}
        <Strip {channel} path={`inputs.${i}`} meterIndex={i} outputIndex={null} />
      {/each}
    {/if}
    {#if nav.side === "all"}<div class="divider"></div>{/if}
    {#if nav.side !== "inputs"}
      {#each device.outputs as channel, i (channel.index)}
        <Strip {channel} path={`outputs.${i}`} meterIndex={inputCount + i} outputIndex={i} />
      {/each}
    {/if}
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
