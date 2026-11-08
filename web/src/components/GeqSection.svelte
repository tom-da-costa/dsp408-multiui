<script lang="ts">
  import { app } from "../lib/app.svelte";
  import { formatDb, formatGeqFreq, GEQ_FREQS, snap } from "../lib/scale";
  import type { InputChannel } from "../lib/types";
  import Field from "./Field.svelte";
  import Section from "./Section.svelte";
  import Slider from "./Slider.svelte";

  interface Props {
    channel: InputChannel;
    path: string;
  }

  let { channel, path }: Props = $props();

  let selected = $state(17); // 1 kHz
  let confirmFlat = $state(false);

  const limits = $derived(app.hello?.limits);
  const editable = $derived(app.editable("geq"));
  const flat = $derived(channel.geq.every((g) => g === 0));

  function setBand(n: number, db: number) {
    void app.set(`${path}.geq.${n}`, db);
  }

  async function resetFlat() {
    confirmFlat = false;
    await Promise.all(channel.geq.map((g, n) => (g === 0 ? true : app.set(`${path}.geq.${n}`, 0))));
  }

  function label(n: number): string {
    return `${formatGeqFreq(GEQ_FREQS[n] ?? 0)} Hz`;
  }
</script>

<Section id="geq" title="Graphic EQ · 31 bands" kind="geq">
  {#snippet actions()}
    {#if confirmFlat}
      <button class="small danger" onclick={resetFlat}>Reset all?</button>
      <button class="small" onclick={() => (confirmFlat = false)}>Cancel</button>
    {:else}
      <button class="small" disabled={!editable || flat} onclick={() => (confirmFlat = true)}
        >Flat</button
      >
    {/if}
  {/snippet}
  {#if limits}
    {@const [min, max] = limits.eq_gain_db}
    <div class="bands" role="group" aria-label="Graphic EQ bands">
      {#each channel.geq as gain, n (n)}
        <div class="band" class:selected={selected === n}>
          <button class="val" onclick={() => (selected = n)} aria-label={`Select ${label(n)}`}
            >{formatDb(gain)}</button
          >
          <div class="slot">
            <Slider
              vertical
              value={gain}
              {min}
              {max}
              origin={0}
              label={`GEQ ${label(n)}`}
              disabled={!editable}
              quantize={(v) => snap(v, min, max, 0.5)}
              onstep={(d) => setBand(n, snap(gain + d * 0.5, min, max, 0.1))}
              onpreview={() => (selected = n)}
              onchange={(v) => setBand(n, v)}
            />
          </div>
          <span class="freq">{formatGeqFreq(GEQ_FREQS[n] ?? 0)}</span>
        </div>
      {/each}
    </div>
    <Field
      label={label(selected)}
      value={channel.geq[selected] ?? 0}
      {min}
      {max}
      unit="dB"
      step={0.5}
      resolution={0.1}
      origin={0}
      format={(v) => formatDb(v)}
      slider={false}
      disabled={!editable}
      onchange={(v) => setBand(selected, v)}
    />
  {/if}
</Section>

<style>
  .bands {
    display: flex;
    gap: 2px;
    overflow-x: auto;
    overscroll-behavior-x: contain;
    padding-bottom: 6px;
    margin-bottom: 6px;
  }
  .band {
    flex: 0 0 40px;
    display: flex;
    flex-direction: column;
    align-items: center;
    border-radius: 6px;
  }
  .band.selected {
    background: var(--panel-2);
  }
  .val {
    min-height: 28px;
    width: 40px;
    padding: 0;
    border: none;
    background: none;
    font-size: 0.7rem;
    font-variant-numeric: tabular-nums;
  }
  .slot {
    height: 180px;
  }
  .freq {
    font-size: 0.7rem;
    color: var(--muted);
    padding: 2px 0 4px;
  }
  .band.selected .freq {
    color: var(--accent);
  }
  .small {
    min-height: 32px;
    padding: 0 10px;
    font-size: 0.85rem;
  }
</style>
