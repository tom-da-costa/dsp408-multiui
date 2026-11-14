<script lang="ts" module>
  import type { Wire } from "../lib/setup";

  export type Selection =
    | { type: "dsp"; output: number }
    | { type: "amp"; id: number }
    | { type: "speaker"; id: number }
    | { type: "wire"; wire: Wire };
</script>

<script lang="ts">
  // Setup wizard, plan: the properties of the element picked on the plan (a DSP output, an
  // amplifier, a speaker, a wire). A speaker's specs are its model's: every cabinet of that
  // model shares them.
  import { formatDb } from "../lib/scale";
  import {
    amplifierModel,
    ampGain,
    disconnect,
    duplicateSpeaker,
    librarySection,
    newSection,
    outputNames,
    RATED_LOADS,
    removeNode,
    removeSection,
    routeOf,
    sameWire,
    setAmpChannels,
    wayLevel,
    wiring,
    type Side,
    type Topology,
  } from "../lib/setup";
  import { wizard } from "../lib/wizard.svelte";

  let { topo, selection = $bindable() }: { topo: Topology; selection: Selection | null } = $props();

  const draft = $derived(wizard.draft);
  const wired = $derived(wiring(draft, topo));
  const ohms = (z: number) => `${Number(z.toFixed(2))} Ω`;
  const dbu = (v: number) => `${formatDb(v)} dBu`;

  const selectedId = (type: "amp" | "speaker"): number | null =>
    selection?.type === type ? selection.id : null;
  const amp = $derived(draft.amps.find((a) => a.id === selectedId("amp")));
  const speaker = $derived(draft.speakers.find((s) => s.id === selectedId("speaker")));
  const kind = $derived(speaker ? draft.kinds.find((k) => k.id === speaker.kind) : undefined);
  const cabinets = $derived(kind ? draft.speakers.filter((s) => s.kind === kind.id).length : 0);

  // Selected DSP output: its route and its way.
  const output = $derived(selection?.type === "dsp" ? selection.output : null);
  const outputWay = $derived(output === null ? undefined : wired.ways.find((w) => w.outputs.includes(output)));
  const route = $derived(output === null ? null : (draft.routes[output] ?? routeOf(draft, output)));
  const routeSource = $derived(draft.sources.find((s) => s.id === route?.source));

  function setRoute(source: number | null, side: Side) {
    if (output === null) return;
    draft.routes[output] = { source, side };
  }

  // Per amplifier channel: what it drives and its limiter.
  function channelInfo(ampId: number, channel: number): string {
    for (const way of wired.ways) {
      const level = wayLevel(draft, way);
      const c = level.channels.find((r) => r.load.amp?.id === ampId && r.load.channel === channel);
      if (!c) continue;
      const limit = c.limiter ? ` · comp ${dbu(c.limiter.compThresholdDbu)}` : "";
      const power = c.powerW ? `, ${c.powerW} W` : ", below its rated loads";
      return `${c.load.cabinets}× ${way.section.name} (${ohms(c.impedanceOhm)}${power})${limit} → Out ${c.load.output + 1}`;
    }
    return "not wired";
  }

  function describeWire(w: Wire): string {
    const ampName = (id: number) => draft.amps.find((a) => a.id === id)?.model ?? "amplifier";
    const spkName = (id: number, section: number) => {
      const k = draft.kinds.find((x) => x.id === draft.speakers.find((s) => s.id === id)?.kind);
      return `${k?.model ?? "speaker"}${k && k.sections.length > 1 ? ` · ${k.sections[section]?.name}` : ""}`;
    };
    if (w.type === "feed") return `Out ${w.output + 1} → ${ampName(w.amp)} ch ${w.channel + 1}`;
    if (w.type === "drive") return `${ampName(w.amp)} ch ${w.channel + 1} → ${spkName(w.speaker, w.section)}`;
    return `Out ${w.output + 1} → ${spkName(w.speaker, w.section)} (active)`;
  }

  function removeWire(w: Wire) {
    disconnect(draft, w);
    selection = null;
  }

  function remove(type: "amp" | "speaker", id: number) {
    removeNode(draft, type, id);
    selection = null;
  }

  function duplicate() {
    if (!speaker) return;
    const copy = duplicateSpeaker(draft, speaker);
    selection = { type: "speaker", id: copy.id };
  }
</script>

{#if selection?.type === "dsp" && output !== null && route}
  <h2>Out {output + 1}</h2>
  {#if outputWay}
    <p class="muted note">
      {outputNames(draft, outputWay).get(output)} — way {outputWay.section.name}, {outputWay.outputs.length > 1
        ? `linked with ${outputWay.outputs.filter((o) => o !== output).map((o) => `Out ${o + 1}`).join(", ")}`
        : "one output"}.
    </p>
  {:else}
    <p class="muted note">Not wired: muted, named Out{output + 1}.</p>
  {/if}
  <div class="field">
    <span>Plays</span>
    <select
      value={route.source ?? ""}
      onchange={(e) => setRoute(Number(e.currentTarget.value) || null, route.side)}
    >
      {#each draft.sources as s (s.id)}<option value={s.id}>{s.name}</option>{/each}
    </select>
  </div>
  {#if routeSource?.stereo}
    <div class="field">
      <span>Side</span>
      <div class="seg" role="group" aria-label="Side">
        {#each [["L", "L"], ["R", "R"], ["LR", "L+R"]] as const as [side, label] (side)}
          <button class:on={route.side === side} onclick={() => setRoute(route.source, side)}>{label}</button>
        {/each}
      </div>
    </div>
    <p class="muted note">L+R sums both sides (mono), the default; L or R for a stereo pair.</p>
  {/if}
{:else if selection?.type === "wire"}
  <h2>Wire</h2>
  <p>{describeWire(selection.wire)}</p>
  {#if draft.wires.some((w) => selection?.type === "wire" && sameWire(w, selection.wire))}
    <button class="danger" onclick={() => selection?.type === "wire" && removeWire(selection.wire)}
      >Remove the wire</button
    >
  {/if}
{:else if amp}
  {@const model = amplifierModel(amp.ref)}
  <h2>Amplifier</h2>
  <label class="field">
    <span>Name</span>
    <input type="text" bind:value={amp.model} />
  </label>
  {#if model}
    <p class="muted note">{model.name}: {model.channels} channels, ratings {model.rating}.</p>
  {:else}
    <label class="field">
      <span>Channels</span>
      <input
        type="number"
        min="1"
        max="16"
        value={amp.channels}
        onchange={(e) => setAmpChannels(draft, amp, Number(e.currentTarget.value))}
      />
    </label>
  {/if}
  <div class="field">
    <span>Given as</span>
    <div class="seg" role="group" aria-label="Gain or sensitivity">
      <button class:on={amp.gainMode === "gain"} onclick={() => (amp.gainMode = "gain")}>Gain</button>
      <button class:on={amp.gainMode === "sensitivity"} onclick={() => (amp.gainMode = "sensitivity")}
        >Sensitivity</button
      >
    </div>
  </div>
  {#if amp.gainMode === "gain"}
    <label class="field">
      <span>Gain</span>
      <input type="text" inputmode="decimal" bind:value={amp.gainDb} />
      <small>dB</small>
    </label>
    {#if model}
      <p class="muted note">
        Datasheet: {model.gains_db.join(" · ")} dB. Enter the real gain of the position you use
        if you know it (e.g. 40.5 dB for "41 dB").
      </p>
    {/if}
  {:else}
    <label class="field">
      <span>Input sensitivity</span>
      <input type="text" inputmode="decimal" bind:value={amp.sensitivityV} />
      <small>V</small>
    </label>
    <label class="field">
      <span>for</span>
      <input type="text" inputmode="decimal" bind:value={amp.sensitivityPowerW} />
      <small>W</small>
    </label>
    <label class="field">
      <span>into</span>
      <input type="text" inputmode="decimal" bind:value={amp.sensitivityOhm} />
      <small>Ω</small>
    </label>
    {#if Number.isFinite(ampGain(amp))}<p class="muted note">A gain of {ampGain(amp).toFixed(1)} dB.</p>{/if}
  {/if}
  <h3>Power per channel <small>(optional)</small></h3>
  {#each RATED_LOADS as load (load)}
    <label class="field">
      <span>into {load} Ω</span>
      <input type="text" inputmode="decimal" bind:value={amp.powerW[load]} placeholder="—" />
      <small>W</small>
    </label>
  {/each}
  <h3>Channels</h3>
  <ul class="list">
    {#each Array.from({ length: amp.channels }, (_, c) => c) as c (c)}
      <li><b>Ch {c + 1}</b> {channelInfo(amp.id, c)}</li>
    {/each}
  </ul>
  <div class="actions">
    <button class="danger" onclick={() => remove("amp", amp.id)}>Remove the amplifier</button>
  </div>
{:else if speaker && kind}
  <h2>Speaker</h2>
  {#if kind.ref === null}
    <label class="field">
      <span>Model</span>
      <input type="text" bind:value={kind.model} />
    </label>
  {:else}
    <p class="muted note">{kind.model}: {cabinets} cabinet{cabinets > 1 ? "s" : ""} in the plan.</p>
  {/if}
  <p class="muted note">
    {cabinets > 1 ? `These settings apply to the ${cabinets} cabinets of this model.` : ""}
  </p>
  {#each kind.sections as section, i (i)}
    {@const lib = librarySection(kind, i)}
    {@const estimated = new Set(lib?.estimated ?? [])}
    <fieldset>
      <legend>{kind.sections.length > 1 ? `Section ${i + 1}` : "Specs"}</legend>
      <label class="field">
        <span>Channel name</span>
        <input type="text" maxlength="8" bind:value={section.name} />
      </label>
      <div class="field">
        <span>Role</span>
        <div class="seg" role="group" aria-label="Role">
          <button class:on={!section.aux} onclick={() => (section.aux = false)}>Main</button>
          <button class:on={section.aux} onclick={() => (section.aux = true)}>Auxiliary</button>
        </div>
      </div>
      <label class="field">
        <span>Range, bottom</span>
        <input type="text" inputmode="decimal" bind:value={section.lowHz} />
        <small>Hz</small>
      </label>
      <label class="field">
        <span>Range, top</span>
        <input type="text" inputmode="decimal" bind:value={section.highHz} />
        <small>Hz</small>
      </label>
      <label class="field">
        <span>Power{#if estimated.has("aes_w")}<em>estimated</em>{/if}</span>
        <input type="text" inputmode="decimal" bind:value={section.aesW} />
        <small>W AES</small>
      </label>
      <label class="field">
        <span>Impedance</span>
        <input type="text" inputmode="decimal" bind:value={section.impedanceOhm} />
        <small>Ω</small>
      </label>
      <label class="field">
        <span>Sensitivity{#if estimated.has("sensitivity_db")}<em>estimated</em>{/if}</span>
        <input type="text" inputmode="decimal" bind:value={section.sensitivityDb} />
        <small>dB 1 W/1 m</small>
      </label>
      <div class="field">
        <span>Load</span>
        <div class="seg" role="group" aria-label="Load">
          <button class:on={section.load === "open"} onclick={() => (section.load = "open")}>Open</button>
          <button class:on={section.load === "closed"} onclick={() => (section.load = "closed")}
            >Closed</button
          >
        </div>
      </div>
      <div class="field">
        <span>Limiter</span>
        <div class="seg" role="group" aria-label="Hard or soft">
          <button class:on={section.mode === "hard"} onclick={() => (section.mode = "hard")}>Hard</button>
          <button class:on={section.mode === "soft"} onclick={() => (section.mode = "soft")}>Soft +2</button>
        </div>
      </div>
      <div class="field">
        <span>0.5 dB step</span>
        <div class="seg" role="group" aria-label="Rounding">
          <button class:on={section.rounding === "up"} onclick={() => (section.rounding = "up")}>Up</button>
          <button class:on={section.rounding === "down"} onclick={() => (section.rounding = "down")}
            >Down</button
          >
        </div>
      </div>
      <label class="check">
        <input type="checkbox" bind:checked={section.phase} /> Inverted polarity
      </label>
      {#if lib}<p class="muted note">{lib.drivers}. {lib.source}</p>{/if}
      {#if kind.ref === null && kind.sections.length > 1}
        <button class="small" onclick={() => removeSection(draft, kind, i)}>Remove this section</button>
      {/if}
    </fieldset>
  {/each}
  {#if kind.ref === null}
    <button class="small" onclick={() => kind.sections.push(newSection(kind.sections.length))}
      >+ Section (bi-amp)</button
    >
  {/if}
  <div class="actions">
    <button onclick={duplicate}>+ Another cabinet</button>
    <button class="danger" onclick={() => remove("speaker", speaker.id)}>Remove</button>
  </div>
{:else}
  <p class="muted">Nothing selected.</p>
{/if}

<style>
  h2 {
    margin-bottom: 6px;
  }
  h3 {
    font-size: 0.95rem;
    margin: 12px 0 6px;
  }
  h3 small {
    color: var(--muted);
    font-weight: 400;
  }
  .field {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 5.4em 4.4em;
    font-size: 0.92rem;
    align-items: center;
    gap: 6px;
    margin: 6px 0;
  }
  .field input {
    text-align: right;
  }
  .field select,
  .field .seg {
    grid-column: 2 / -1;
    min-width: 0;
  }
  .field .seg button {
    flex: 1;
    padding: 0 4px;
    white-space: nowrap;
  }
  input[type="number"] {
    min-height: var(--tap);
    padding: 0 8px;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: var(--bg);
    width: 100%;
  }
  .field input[type="text"]:not([inputmode]) {
    grid-column: 2 / -1;
    text-align: left;
  }
  small {
    color: var(--muted);
    font-size: 0.72rem;
  }
  em {
    margin-left: 6px;
    color: var(--warn);
    font-style: normal;
    font-size: 0.75rem;
  }
  .note {
    font-size: 0.8rem;
    margin: 4px 0;
  }
  fieldset {
    border: 1px solid var(--line);
    border-radius: 8px;
    margin: 8px 0;
    padding: 4px 10px 8px;
  }
  legend {
    color: var(--muted);
    font-size: 0.85rem;
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
  .list {
    margin: 0;
    padding-left: 16px;
    font-size: 0.8rem;
    display: grid;
    gap: 4px;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 12px;
  }
  button.small {
    min-height: 36px;
    font-size: 0.85rem;
  }
</style>
