<script lang="ts">
  import { app } from "../lib/app.svelte";
  import { formatHz } from "../lib/scale";
  import type { Channel, Filter } from "../lib/types";
  import Field from "./Field.svelte";
  import Section from "./Section.svelte";

  interface Props {
    channel: Channel;
    path: string;
    id?: string;
    title?: string;
  }

  let { channel, path, id = "crossover", title = "High-pass / low-pass" }: Props = $props();

  const profile = $derived(app.hello?.profile);
  const editable = $derived(app.editable("crossover"));
  const FILTERS = [
    ["hpf", "High-pass"],
    ["lpf", "Low-pass"],
  ] as const;

  function setFilter(which: "hpf" | "lpf", change: Partial<Filter>) {
    void app.set(`${path}.crossover.${which}`, change);
  }
</script>

<Section {id} {title} kind="crossover">
  {#if profile}
    {#each FILTERS as [which, title] (which)}
      {@const filter = channel.crossover[which]}
      <div class="filter" class:off={!filter.enabled}>
        <div class="head">
          <strong>{title}</strong>
          <select
            value={filter.slope}
            disabled={!editable}
            aria-label={`${title} slope`}
            onchange={(e) => setFilter(which, { slope: Number((e.currentTarget as HTMLSelectElement).value) })}
          >
            {#each profile.slopes as name, i (i)}
              {#if i > 0}<option value={i}>{name}</option>{/if}
            {/each}
          </select>
          <button
            class="switch"
            class:on={filter.enabled}
            disabled={!editable}
            aria-pressed={filter.enabled}
            aria-label={`${title} ${filter.enabled ? "on" : "off"}`}
            onclick={() => setFilter(which, { enabled: !filter.enabled })}
            >{filter.enabled ? "On" : "Off"}</button
          >
        </div>
        <Field
          label="Frequency"
          value={filter.freq_hz}
          min={profile.freq_min_hz}
          max={profile.freq_max_hz}
          unit="Hz"
          scale="log"
          factor={2 ** (1 / 6)}
          step={0.1}
          format={formatHz}
          disabled={!editable}
          onchange={(v) => setFilter(which, { freq_hz: v })}
        />
      </div>
    {/each}
    <p class="hint muted">Off bypasses the filter; the slope is kept for when it is turned back on.</p>
  {/if}
</Section>

<style>
  .filter + .filter {
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px solid var(--line);
  }
  .head {
    display: grid;
    grid-template-columns: 1fr minmax(96px, 120px) auto;
    align-items: center;
    gap: 8px;
  }
  .head select {
    min-height: 36px;
  }
  .filter.off :global(.num) {
    color: var(--muted);
  }
  .hint {
    font-size: 0.8rem;
    margin: 8px 0 0;
  }
</style>
