<script lang="ts">
  // Setup wizard, step 3: the crossovers between the main ways (proposed from the speakers'
  // ranges, editable), the subsonic high-pass of the lowest way and the auxiliary ways' filters.
  import { boundaries, mainWays, wiring, type FilterSetting, type Topology } from "../lib/setup";
  import { wizard } from "../lib/wizard.svelte";

  let { topo }: { topo: Topology } = $props();

  const draft = $derived(wizard.draft);
  const ways = $derived(wiring(draft, topo).ways);
  const main = $derived(mainWays(ways));
  const lowest = $derived(main[0]);
  const highest = $derived(main[main.length - 1]);
  const bounds = $derived(boundaries(ways));
  const auxWays = $derived(ways.filter((w) => w.props.aux));
  const slopeOptions = $derived(topo.slopes.map((name, i) => ({ name, i })).slice(1));
  const hz = (v: number) => (Number.isFinite(v) ? String(Math.round(v)) : "?");
  const range = (way: { lowHz: number; highHz: number }) => `${hz(way.lowHz)}–${hz(way.highHz)} Hz`;
  const known = (v: number) => (Number.isFinite(v) && v > 0 ? Math.round(v) : null);
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
    <h3>{lowest.key} <small>{range(lowest)}</small></h3>
    {@render filter(draft.subsonic, "Subsonic high-pass", known(lowest.lowHz))}
    <p class="muted note">Protects the lowest way below its range (the cone's excursion).</p>
  {/if}
  {#each bounds as b (b.key)}
    {@const setting = draft.crossovers[b.key]}
    <h3>
      {b.lower.key} ↔ {b.upper.key}
      <small>{range(b.lower)} · {range(b.upper)}</small>
    </h3>
    {#if setting}{@render filter(setting, "Crossover", b.proposedHz)}{/if}
    {#if b.gap}
      <p class="warn note">The two ranges do not meet: there is a hole around the crossover.</p>
    {/if}
  {/each}
  {#if highest}
    <p class="muted note">{highest.key}: no low-pass, it plays up to the top of its range.</p>
  {/if}
</section>

{#if auxWays.length}
  <section class="card">
    <h2>Auxiliary outputs</h2>
    <p class="muted hint">Filtered to their speakers' range, Butterworth 24 dB/oct.</p>
    {#each auxWays as way (way.key)}
      {@const setting = draft.aux[way.key]}
      <h3>{way.key} <small>{range(way)}</small></h3>
      {#if setting}
        {@render filter(setting.hpf, "High-pass", known(way.lowHz))}
        {@render filter(setting.lpf, "Low-pass", known(way.highHz))}
      {/if}
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
