<script lang="ts">
  // Setup wizard, step 4: the crossovers between the main ways (proposed from the speakers'
  // ranges, editable), the subsonic high-pass of the lowest way and the auxiliary ways' filters.
  import {
    auxSetting,
    boundaries,
    mainWays,
    num,
    type FilterSetting,
    type Topology,
  } from "../lib/setup";
  import { wizard } from "../lib/wizard.svelte";

  let { topo }: { topo: Topology } = $props();

  const draft = $derived(wizard.draft);
  const main = $derived(mainWays(draft));
  const lowest = $derived(main[0]);
  const highest = $derived(main[main.length - 1]);
  const bounds = $derived(boundaries(draft));
  const auxWays = $derived(draft.ways.filter((w) => w.aux));
  const slopeOptions = $derived(topo.slopes.map((name, i) => ({ name, i })).slice(1));
  const range = (low: string, high: string) => `${low || "?"}–${high || "?"} Hz`;
</script>

{#snippet filter(setting: FilterSetting, label: string, proposed: number | null)}
  <div class="filter">
    <label class="check">
      <input type="checkbox" bind:checked={setting.enabled} />
      <span>{label}</span>
    </label>
    <label class="freq">
      <input
        type="text"
        inputmode="decimal"
        aria-label={`${label} frequency`}
        disabled={!setting.enabled}
        placeholder={proposed === null ? "—" : String(proposed)}
        bind:value={setting.freqHz}
      />
      <small>Hz</small>
    </label>
    <select aria-label={`${label} slope`} disabled={!setting.enabled} bind:value={setting.slope}>
      {#each slopeOptions as option (option.i)}
        <option value={option.i}>{option.name}</option>
      {/each}
    </select>
  </div>
{/snippet}

<section class="card">
  <h2>Crossovers</h2>
  <p class="muted hint">
    Proposed where the speakers' ranges meet (the geometric mean of the top of the lower way and
    the bottom of the upper one), Linkwitz-Riley 24 dB/oct. An empty frequency takes the proposal.
  </p>
  {#if lowest}
    <h3>{lowest.name} <small>{range(lowest.speaker.lowHz, lowest.speaker.highHz)}</small></h3>
    {@render filter(draft.subsonic, "Subsonic high-pass", num(lowest.speaker.lowHz) || null)}
    <p class="muted note">Protects the lowest way below its range (the cone's excursion).</p>
  {/if}
  {#each bounds as b (b.key)}
    {@const setting = draft.crossovers[b.key]}
    <h3>
      {b.lower.name} ↔ {b.upper.name}
      <small
        >{range(b.lower.speaker.lowHz, b.lower.speaker.highHz)} · {range(
          b.upper.speaker.lowHz,
          b.upper.speaker.highHz,
        )}</small
      >
    </h3>
    {#if setting}{@render filter(setting, "Crossover", b.proposedHz)}{/if}
    {#if b.gap}
      <p class="warn note">The two ranges do not meet: there is a hole around the crossover.</p>
    {/if}
  {/each}
  {#if highest && main.length > 0}
    <p class="muted note">{highest.name}: no low-pass, it plays up to the top of its range.</p>
  {/if}
</section>

{#if auxWays.length}
  <section class="card">
    <h2>Auxiliary outputs</h2>
    <p class="muted hint">Filtered to their speakers' range, Butterworth 24 dB/oct.</p>
    {#each auxWays as way (way.id)}
      {@const setting = draft.aux[way.id] ?? auxSetting(draft, way, topo.slopes)}
      <h3>{way.name} <small>{range(way.speaker.lowHz, way.speaker.highHz)}</small></h3>
      {@render filter(setting.hpf, "High-pass", num(way.speaker.lowHz) || null)}
      {@render filter(setting.lpf, "Low-pass", num(way.speaker.highHz) || null)}
    {/each}
  </section>
{/if}

<style>
  .hint {
    font-size: 0.85rem;
    margin: 0 0 6px;
  }
  h3 {
    font-size: 0.95rem;
    margin: 14px 0 6px;
  }
  h3 small {
    color: var(--muted);
    font-weight: 400;
    font-size: 0.8rem;
  }
  .filter {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 7.5em 6.5em;
    align-items: center;
    gap: 8px;
    max-width: 520px;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: var(--tap);
    font-size: 0.9rem;
  }
  .check input {
    flex: none;
    width: 20px;
    height: 20px;
  }
  .freq {
    display: grid;
    grid-template-columns: 1fr auto;
    align-items: center;
    gap: 4px;
  }
  .freq input {
    text-align: right;
  }
  small {
    color: var(--muted);
    font-size: 0.75rem;
  }
  .note {
    margin: 4px 0 0;
    font-size: 0.8rem;
  }
  .warn {
    color: var(--warn);
  }
</style>
