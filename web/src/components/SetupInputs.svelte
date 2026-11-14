<script lang="ts">
  // Setup wizard, step 1: the sources (stereo or mono, they take the inputs in order) and the
  // optional low shelf on the inputs.
  import { inputsNeeded, sourceInputs, type Topology } from "../lib/setup";
  import { wizard } from "../lib/wizard.svelte";

  let { topo }: { topo: Topology } = $props();

  const draft = $derived(wizard.draft);
  const inputsOf = $derived(sourceInputs(draft));
  const free = $derived(topo.inputs - inputsNeeded(draft));
  const letter = (i: number) => String.fromCharCode(65 + i);

  function add(stereo: boolean) {
    const n = draft.sources.length + 1;
    draft.sources.push({ id: draft.nextId++, name: stereo ? `Src${n}` : `Mic${n}`, stereo });
  }

  function remove(id: number) {
    draft.sources = draft.sources.filter((s) => s.id !== id);
    for (const way of draft.ways) way.sources = way.sources.filter((s) => s !== id);
  }

  function inputsLabel(id: number): string {
    const ins = inputsOf.get(id) ?? [];
    return ins.map((i) => (i < topo.inputs ? `In ${letter(i)}` : "—")).join(" + ");
  }
</script>

<section class="card">
  <h2>Sources</h2>
  <p class="muted hint">
    What comes into the DSP. A stereo source takes two inputs, linked; the sources take the
    inputs in order. A channel name holds 8 characters: " L" and " R" are added to a stereo
    source's name.
  </p>
  <div class="rows">
    {#each draft.sources as source (source.id)}
      <div class="row">
        <input
          type="text"
          aria-label="Source name"
          maxlength={source.stereo ? 6 : 8}
          bind:value={source.name}
        />
        <div class="seg" role="group" aria-label="Stereo or mono">
          <button class:on={source.stereo} onclick={() => (source.stereo = true)}>Stereo</button>
          <button
            class:on={!source.stereo}
            onclick={() => (source.stereo = false)}>Mono</button
          >
        </div>
        <span class="ins">{inputsLabel(source.id)}</span>
        <button class="remove" aria-label={`Remove ${source.name}`} onclick={() => remove(source.id)}
          >✕</button
        >
      </div>
    {/each}
  </div>
  <div class="add">
    <button disabled={free < 2} onclick={() => add(true)}>+ Stereo source</button>
    <button disabled={free < 1} onclick={() => add(false)}>+ Mono source</button>
    <span class="muted">{Math.max(0, free)} of {topo.inputs} inputs free</span>
  </div>
</section>

<section class="card">
  <h2>Input EQ</h2>
  <label class="check">
    <input type="checkbox" bind:checked={draft.lowShelf.enabled} />
    Low shelf on the inputs
    <small>a bass lift (or cut) on every source, on the inputs' first PEQ band</small>
  </label>
  {#if draft.lowShelf.enabled}
    <div class="fields">
      <label>
        <span>Frequency</span>
        <input type="text" inputmode="decimal" bind:value={draft.lowShelf.freqHz} />
        <small>Hz</small>
      </label>
      <label>
        <span>Gain</span>
        <input type="text" inputmode="decimal" bind:value={draft.lowShelf.gainDb} />
        <small>dB</small>
      </label>
    </div>
  {/if}
</section>

<style>
  .hint {
    font-size: 0.85rem;
    margin: 0 0 10px;
  }
  .rows {
    display: grid;
    gap: 6px;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .row input {
    flex: 1 1 9em;
    width: auto;
    min-width: 0;
  }
  .remove {
    width: var(--tap);
  }
  .ins {
    font-size: 0.8rem;
    color: var(--muted);
    white-space: nowrap;
  }
  .remove {
    padding: 0;
    margin-left: auto;
  }
  .add {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin-top: 10px;
  }
  .add span {
    font-size: 0.85rem;
  }
  .check {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 8px;
    min-height: 36px;
  }
  .check input {
    width: 20px;
    height: 20px;
  }
  .check small {
    flex-basis: 100%;
    padding-left: 28px;
  }
  small {
    color: var(--muted);
    font-size: 0.75rem;
  }
  .fields {
    display: grid;
    gap: 8px;
    margin-top: 8px;
    max-width: 360px;
  }
  .fields label {
    display: grid;
    grid-template-columns: 1fr 7em 2.5em;
    align-items: center;
    gap: 8px;
  }
  .fields input {
    text-align: right;
  }
</style>
