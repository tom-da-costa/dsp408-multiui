<script lang="ts">
  import { app } from "../lib/app.svelte";
  import Strip from "./Strip.svelte";

  let filter = $state<"all" | "in" | "out">("all");
  const device = $derived(app.device);
  const inputCount = $derived(app.hello?.profile.input_count ?? 4);
</script>

{#if device}
  <div class="filters" role="tablist">
    {#each [["all", "All"], ["in", "Inputs"], ["out", "Outputs"]] as [key, text] (key)}
      <button
        role="tab"
        aria-selected={filter === key}
        class:selected={filter === key}
        onclick={() => (filter = key as typeof filter)}>{text}</button
      >
    {/each}
  </div>
  <div class="strips">
    {#if filter !== "out"}
      {#each device.inputs as channel, i (channel.index)}
        <Strip {channel} path={`inputs.${i}`} meterIndex={i} outputIndex={null} />
      {/each}
    {/if}
    {#if filter === "all"}<div class="divider"></div>{/if}
    {#if filter !== "in"}
      {#each device.outputs as channel, i (channel.index)}
        <Strip {channel} path={`outputs.${i}`} meterIndex={inputCount + i} outputIndex={i} />
      {/each}
    {/if}
  </div>
{/if}

<style>
  .filters {
    display: flex;
    gap: 6px;
    padding: 0 0 10px;
  }
  .filters button {
    min-height: 36px;
    border-radius: 18px;
  }
  .filters .selected {
    background: var(--accent);
    color: var(--accent-text);
    border-color: var(--accent);
  }
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
