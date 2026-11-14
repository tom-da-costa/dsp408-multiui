<script lang="ts">
  // Setup wizard, step 2: the ways of the system (a speaker from the library, or typed in),
  // mono or stereo, main or auxiliary, the sources they play, polarity, and their outputs.
  import {
    blankSpeaker,
    channelNames,
    mainWays,
    newWay,
    speakerFromLibrary,
    SPEAKERS,
    wayOutputs,
    type Topology,
    type Way,
  } from "../lib/setup";
  import { wizard } from "../lib/wizard.svelte";

  let { topo }: { topo: Topology } = $props();

  const draft = $derived(wizard.draft);
  const outputs = $derived(wayOutputs(draft, topo.outputs));
  const order = $derived(mainWays(draft).map((w) => w.id));
  let pick = $state(SPEAKERS[0]?.id ?? "");

  function uniqueName(base: string): string {
    const taken = new Set(draft.ways.map((w) => w.name));
    if (!taken.has(base)) return base;
    for (let n = 2; ; n++) if (!taken.has(`${base.slice(0, 5)}${n}`)) return `${base.slice(0, 5)}${n}`;
  }

  function add(aux = false) {
    const all = draft.sources.map((s) => s.id);
    const model = SPEAKERS.find((m) => m.id === pick);
    if (aux || !model) {
      const way = newWay(draft.nextId++, uniqueName(aux ? "Mon" : "Way"), blankSpeaker(), all);
      way.aux = aux;
      draft.ways.push(way);
      return;
    }
    model.sections.forEach((section, i) => {
      const name = uniqueName(section.name.slice(0, 6));
      draft.ways.push(newWay(draft.nextId++, name, speakerFromLibrary(model, i), all));
    });
  }

  function remove(id: number) {
    draft.ways = draft.ways.filter((w) => w.id !== id);
  }

  function setStereo(way: Way, stereo: boolean) {
    way.stereo = stereo;
    way.outputs = null; // another number of outputs: back to the automatic order
  }

  function toggleSource(way: Way, id: number) {
    way.sources = way.sources.includes(id)
      ? way.sources.filter((s) => s !== id)
      : [...way.sources, id];
  }

  function setOutput(way: Way, side: number, value: number) {
    if (value < 0) {
      way.outputs = null;
      return;
    }
    const current = [...(outputs.get(way.id) ?? [])];
    current[side] = value;
    way.outputs = current;
  }

  const sideLabel = (way: Way, side: number) => (way.stereo ? (side === 0 ? "L" : "R") : "");
</script>

<section class="card">
  <h2>Ways</h2>
  <p class="muted hint">
    One way per kind of speaker (sub, kick, mid, high…), in any order: the wizard sorts the
    main ways from low to high by their range. A cabinet driven bi-amp adds one way per section.
    Auxiliary outputs (monitors, fills, delay towers) are not part of the crossover chain.
  </p>
  <div class="add">
    <select aria-label="Speaker from the library" bind:value={pick}>
      {#each SPEAKERS as model (model.id)}
        <option value={model.id}>{model.name} — {model.description}</option>
      {/each}
      <option value="">Other speaker (typed in)</option>
    </select>
    <button class="primary" onclick={() => add()}>+ Way</button>
    <button onclick={() => add(true)}>+ Auxiliary output</button>
  </div>
</section>

{#each draft.ways as way (way.id)}
  {@const outs = outputs.get(way.id) ?? []}
  <section class="card way">
    <div class="top">
      <input
        type="text"
        class="name"
        aria-label="Way name"
        maxlength={way.stereo ? 6 : 8}
        bind:value={way.name}
      />
      <span class="tag" class:aux={way.aux}>
        {way.aux ? "Auxiliary" : `Way ${order.indexOf(way.id) + 1} of ${order.length}`}
      </span>
      <button class="remove" aria-label={`Remove ${way.name}`} onclick={() => remove(way.id)}
        >✕</button
      >
    </div>
    <p class="speaker muted">{way.speaker.label || "Speaker typed in at the next step"}</p>

    <div class="grid">
      <span class="label">Channels</span>
      <div class="seg" role="group" aria-label="Mono or stereo">
        <button class:on={!way.stereo} onclick={() => setStereo(way, false)}>Mono</button>
        <button class:on={way.stereo} onclick={() => setStereo(way, true)}>Stereo</button>
      </div>

      <span class="label">Role</span>
      <div class="seg" role="group" aria-label="Main or auxiliary">
        <button class:on={!way.aux} onclick={() => (way.aux = false)}>Main</button>
        <button class:on={way.aux} onclick={() => (way.aux = true)}>Auxiliary</button>
      </div>

      <span class="label">Plays</span>
      <div class="chips" role="group" aria-label="Sources">
        {#each draft.sources as source (source.id)}
          <button
            class="switch"
            class:on={way.sources.includes(source.id)}
            aria-pressed={way.sources.includes(source.id)}
            onclick={() => toggleSource(way, source.id)}>{source.name}</button
          >
        {/each}
      </div>

      <span class="label">Outputs</span>
      <div class="outs">
        {#each outs as o, side (side)}
          <label>
            {#if way.stereo}<span>{sideLabel(way, side)}</span>{/if}
            <select
              aria-label={`Output ${channelNames(way.name, way.stereo)[side]}`}
              value={way.outputs?.[side] ?? -1}
              onchange={(e) => setOutput(way, side, Number(e.currentTarget.value))}
            >
              <option value={-1}>Auto ({o >= 0 && o < topo.outputs ? `Out ${o + 1}` : "none"})</option>
              {#each Array.from({ length: topo.outputs }, (_, n) => n) as n (n)}
                <option value={n}>Out {n + 1}</option>
              {/each}
            </select>
          </label>
        {/each}
      </div>

      <span class="label">Polarity</span>
      <label class="check">
        <input type="checkbox" bind:checked={way.phase} /> Inverted
      </label>
    </div>
    {#if way.stereo && draft.sources.some((s) => way.sources.includes(s.id) && !s.stereo)}
      <p class="muted note">A mono source plays on both sides.</p>
    {/if}
    {#if !way.stereo && draft.sources.some((s) => way.sources.includes(s.id) && s.stereo)}
      <p class="muted note">A stereo source is summed (L + R) on this mono way.</p>
    {/if}
  </section>
{/each}

<style>
  .hint {
    font-size: 0.85rem;
    margin: 0 0 10px;
  }
  .add {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .add select {
    grid-column: 1 / -1;
  }
  .way {
    display: grid;
    gap: 8px;
  }
  .top {
    display: grid;
    grid-template-columns: minmax(0, 10em) 1fr var(--tap);
    align-items: center;
    gap: 8px;
  }
  .name {
    font-weight: 600;
  }
  .tag {
    font-size: 0.8rem;
    color: var(--muted);
  }
  .tag.aux {
    color: var(--info);
  }
  .remove {
    padding: 0;
  }
  .speaker {
    margin: 0;
    font-size: 0.85rem;
  }
  .grid {
    display: grid;
    grid-template-columns: 5.5em minmax(0, 1fr);
    align-items: center;
    gap: 8px;
  }
  .label {
    color: var(--muted);
    font-size: 0.85rem;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .outs {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
  .outs label {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .outs select {
    width: auto;
  }
  .check {
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: 36px;
  }
  .check input {
    width: 20px;
    height: 20px;
  }
  .note {
    margin: 0;
    font-size: 0.8rem;
  }
</style>
