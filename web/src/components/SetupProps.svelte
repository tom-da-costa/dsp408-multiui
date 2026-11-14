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
  // amplifier, a speaker, a wire). Each speaker has its own specs and side; the settings of a
  // way (by channel name) are shared by every cabinet and output of that way.
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
    setWayProp,
    wayLevel,
    wayProps,
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
  const SIDES: [Side, string][] = [
    ["L", "Left"],
    ["R", "Right"],
    ["LR", "Mono L+R"],
  ];

  // Selected DSP output: its source, its side (from its speakers) and its way.
  const output = $derived(selection?.type === "dsp" ? selection.output : null);
  const outputWay = $derived(
    output === null ? undefined : wired.ways.find((w) => w.outputs.includes(output)),
  );
  const source = $derived(output === null ? null : routeOf(draft, output));
  const side = $derived(output === null ? "LR" : (wired.sideOf.get(output) ?? "LR"));

  // Per amplifier channel: what it drives and its limiter.
  function channelInfo(ampId: number, channel: number): string {
    for (const way of wired.ways) {
      const level = wayLevel(draft, way, wired.sideOf);
      const c = level.channels.find((r) => r.load.amp?.id === ampId && r.load.channel === channel);
      if (!c) continue;
      const limit = c.limiter ? ` · comp ${dbu(c.limiter.compThresholdDbu)}` : "";
      const power = c.powerW ? `, ${c.powerW} W` : ", below its rated loads";
      return `${c.load.cabinets.length}× ${way.key} (${ohms(c.impedanceOhm)}${power})${limit} → Out ${c.load.output + 1}`;
    }
    return "not wired";
  }

  function describeWire(w: Wire): string {
    const ampName = (id: number) => draft.amps.find((a) => a.id === id)?.model ?? "amplifier";
    const spkName = (id: number, section: number) => {
      const k = draft.speakers.find((s) => s.id === id);
      return `${k?.model ?? "speaker"}${k && k.sections.length > 1 ? ` · ${k.sections[section]?.name}` : ""}`;
    };
    if (w.type === "feed") return `Out ${w.output + 1} → ${ampName(w.amp)} ch ${w.channel + 1}`;
    if (w.type === "drive") return `${ampName(w.amp)} ch ${w.channel + 1} → ${spkName(w.speaker, w.section)}`;
    if (w.type === "chain")
      return `${spkName(w.from, w.fromSection)} → ${spkName(w.speaker, w.section)} (bridged, in parallel)`;
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

{#if selection?.type === "dsp" && output !== null}
  <h2>Out {output + 1}</h2>
  {#if outputWay}
    <p class="muted note">
      {outputNames(outputWay, wired.sideOf).get(output)} — way {outputWay.key}, {outputWay.outputs.length > 1
        ? `linked with ${outputWay.outputs.filter((o) => o !== output).map((o) => `Out ${o + 1}`).join(", ")}`
        : "one output"}.
    </p>
  {:else}
    <p class="muted note">Not wired: muted, named Out{output + 1}.</p>
  {/if}
  <div class="field">
    <span>Plays</span>
    <select
      value={source ?? ""}
      onchange={(e) => (draft.routes[output] = Number(e.currentTarget.value) || null)}
    >
      {#each draft.sources as s (s.id)}<option value={s.id}>{s.name}</option>{/each}
    </select>
  </div>
  {#if outputWay}
    <p class="muted note">
      Side: <strong>{side === "LR" ? "L+R (mono)" : side === "L" ? "left" : "right"}</strong>, from
      its speakers (set the side on a speaker).
    </p>
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
{:else if speaker}
  <h2>Speaker</h2>
  <label class="field">
    <span>Model</span>
    <input type="text" bind:value={speaker.model} />
  </label>
  <div class="field">
    <span>Side</span>
    <div class="seg" role="group" aria-label="Side">
      {#each SIDES as [value, label] (value)}
        <button class:on={speaker.side === value} onclick={() => (speaker.side = value)}>{label}</button>
      {/each}
    </div>
  </div>
  <p class="muted note">
    Left or right for one speaker of a stereo pair; mono plays L+R. Its outputs play that side.
    A copy takes the other side.
  </p>
  {#each speaker.sections as section, i (i)}
    {@const lib = librarySection(speaker, i)}
    {@const estimated = new Set(lib?.estimated ?? [])}
    {@const props = wayProps(draft, section.name)}
    <fieldset>
      <legend>{speaker.sections.length > 1 ? `Section ${i + 1}` : "This speaker"}</legend>
      <label class="field">
        <span>Channel name</span>
        <input type="text" maxlength="8" bind:value={section.name} />
      </label>
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
      {#if lib}<p class="muted note">{lib.drivers}. {lib.source}</p>{/if}

      <h3>Way "{section.name}" <small>shared by its cabinets and outputs</small></h3>
      <div class="field">
        <span>Role</span>
        <div class="seg" role="group" aria-label="Role">
          <button class:on={!props.aux} onclick={() => setWayProp(draft, section.name, "aux", false)}
            >Main</button
          >
          <button class:on={props.aux} onclick={() => setWayProp(draft, section.name, "aux", true)}
            >Auxiliary</button
          >
        </div>
      </div>
      <div class="field">
        <span>Limiter</span>
        <div class="seg" role="group" aria-label="Hard or soft">
          <button class:on={props.mode === "hard"} onclick={() => setWayProp(draft, section.name, "mode", "hard")}
            >Hard</button
          >
          <button class:on={props.mode === "soft"} onclick={() => setWayProp(draft, section.name, "mode", "soft")}
            >Soft +2</button
          >
        </div>
      </div>
      <div class="field">
        <span>0.5 dB step</span>
        <div class="seg" role="group" aria-label="Rounding">
          <button
            class:on={props.rounding === "up"}
            onclick={() => setWayProp(draft, section.name, "rounding", "up")}>Up</button
          >
          <button
            class:on={props.rounding === "down"}
            onclick={() => setWayProp(draft, section.name, "rounding", "down")}>Down</button
          >
        </div>
      </div>
      <label class="check">
        <input
          type="checkbox"
          checked={props.phase}
          onchange={(e) => setWayProp(draft, section.name, "phase", e.currentTarget.checked)}
        /> Inverted polarity
      </label>
      {#if speaker.ref === null && speaker.sections.length > 1}
        <button class="small" onclick={() => removeSection(draft, speaker, i)}>Remove this section</button>
      {/if}
    </fieldset>
  {/each}
  {#if speaker.ref === null}
    <button class="small" onclick={() => speaker.sections.push(newSection(speaker.sections.length))}
      >+ Section (bi-amp)</button
    >
  {/if}
  <div class="actions">
    <button onclick={duplicate}>+ Copy</button>
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
