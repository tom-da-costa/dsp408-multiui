<script lang="ts">
  // Setup wizard, step 5: everything the wizard will write, the output gains (computed, can be
  // typed over), the optional low shelf on the inputs, the preset slot, then the write: outputs muted while it runs, every input left
  // muted at the end (the user lets the sound in from the Live view).
  import { app } from "../lib/app.svelte";
  import { nav } from "../lib/nav.svelte";
  import { formatDb } from "../lib/scale";
  import {
    buildPlan,
    sourceInputs,
    storeErrors,
    wayFilters,
    wayGains,
    wayLevel,
    wayOutputs,
    type Filter,
    type Topology,
  } from "../lib/setup";
  import { wizard } from "../lib/wizard.svelte";

  let { topo }: { topo: Topology } = $props();

  const draft = $derived(wizard.draft);
  const outs = $derived(wayOutputs(draft, topo.outputs));
  const filters = $derived(wayFilters(draft, topo.slopes));
  const gains = $derived(wayGains(draft));
  const inputsOf = $derived(sourceInputs(draft));
  const errors = $derived(storeErrors(draft, topo));
  const presets = $derived(app.device?.presets ?? []);
  const slotName = $derived(presets.find((p) => p.slot === draft.slot)?.name ?? "");
  let confirming = $state(false);
  let busy = $state(false);
  let done = $state<string[] | null>(null);

  const letter = (i: number) => String.fromCharCode(65 + i);
  const label = (slot: number) => `U${String(slot).padStart(2, "0")}`;
  const describe = (f: Filter | null | undefined) =>
    f ? `${Math.round(f.freq_hz)} Hz ${topo.slopes[f.slope] ?? ""}` : "—";
  const outLabel = (list: number[]) =>
    list.map((o) => (o >= 0 && o < topo.outputs ? `Out ${o + 1}` : "no output")).join(" + ");

  function playsLabel(sourceIds: number[], stereo: boolean): string {
    return draft.sources
      .filter((s) => sourceIds.includes(s.id))
      .map((s) => {
        const ins = (inputsOf.get(s.id) ?? []).map(letter).join("+");
        const [l, r] = (inputsOf.get(s.id) ?? []).map(letter);
        if (s.stereo && stereo) return `${s.name} (${l}→L, ${r}→R)`;
        return `${s.name} (${s.stereo ? `${ins} summed` : ins})`;
      })
      .join(", ");
  }

  async function apply() {
    busy = true;
    const result = await app.call({
      type: "setup.apply",
      plan: buildPlan(draft, topo),
      slot: draft.slot,
      name: draft.presetName,
    });
    busy = false;
    confirming = false;
    if (!result.ok) return;
    app.toast(`Setup written and stored to ${label(draft.slot)}`);
    done = result.notes ?? [];
  }
</script>

{#if done}
  <section class="card done">
    <h2>Setup written</h2>
    <p>
      Stored to <strong>{label(draft.slot)} "{draft.presetName}"</strong>. The outputs in use are
      on; <strong>every input is muted</strong>: check the system, then unmute the inputs in the
      Live view, quietly first.
    </p>
    {#each done as note (note)}<p class="warn">{note}</p>{/each}
    <div class="actions">
      <button class="primary" onclick={() => nav.select("live")}>Go to Live</button>
      <button onclick={() => (done = null)}>Back to the summary</button>
    </div>
  </section>
{:else}
  <section class="card">
    <h2>Outputs</h2>
    <p class="muted hint">
      Output gains match the main ways' levels: for the same input, every way gives the same SPL
      at 1 m (the loudest are turned down). Type a gain to replace it.
    </p>
    <div class="ways">
      {#each draft.ways as way (way.id)}
        {@const level = wayLevel(way)}
        {@const gain = gains.get(way.id)}
        {@const f = filters.get(way.id)}
        <article class="way">
          <h3>
            {way.name}
            <small>{outLabel(outs.get(way.id) ?? [])}{way.stereo ? ", linked" : ""}</small>
          </h3>
          <dl>
            <dt>Plays</dt>
            <dd>{playsLabel(way.sources, way.stereo)}</dd>
            <dt>High-pass</dt>
            <dd class="nowrap">{describe(f?.hpf)}</dd>
            <dt>Low-pass</dt>
            <dd class="nowrap">{describe(f?.lpf)}</dd>
            <dt>Comp · limit</dt>
            <dd class="nowrap">
              {level.limiter
                ? `${formatDb(level.limiter.compThresholdDbu)} · ${formatDb(level.limiter.limitThresholdDbu)} dBu`
                : "off"}
            </dd>
            {#if level.splMaxDb !== null}
              <dt>SPL max</dt>
              <dd>{level.splMaxDb.toFixed(1)} dB</dd>
            {/if}
            <dt>Polarity</dt>
            <dd>{way.phase ? "inverted" : "normal"}</dd>
          </dl>
          <label class="gain">
            <span>Output gain</span>
            <input
              type="text"
              inputmode="decimal"
              aria-label={`${way.name} output gain`}
              placeholder={gain ? formatDb(gain.computed) : "0"}
              bind:value={way.gainDb}
            />
            <small>dB</small>
          </label>
        </article>
      {/each}
    </div>
    <p class="muted note">
      The other outputs are muted and named Out N. Delays are 0, EQs flat, no gate.
    </p>
  </section>

  <section class="card">
    <h2>Inputs</h2>
    <ul class="inputs">
      {#each draft.sources as source (source.id)}
        <li>
          <strong>{source.name}</strong>
          on {(inputsOf.get(source.id) ?? []).map((i) => `In ${letter(i)}`).join(" + ")}{source.stereo
            ? ", linked"
            : ""}
        </li>
      {/each}
    </ul>
    <p class="muted note">Every input ends muted: you let the sound in once the system is checked.</p>
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

  <section class="card">
    <h2>Store</h2>
    <div class="store">
      <label>
        <span>Preset slot</span>
        <select bind:value={draft.slot}>
          <option value={0} disabled>Pick a slot…</option>
          {#each presets as preset (preset.slot)}
            <option value={preset.slot}>{label(preset.slot)} — {preset.name}</option>
          {/each}
        </select>
      </label>
      <label>
        <span>Preset name</span>
        <input type="text" maxlength="14" bind:value={draft.presetName} />
      </label>
    </div>
    {#each errors as error (error)}<p class="warn">{error}</p>{/each}

    {#if confirming}
      <div class="confirm">
        <p>
          <strong>Every setting of the DSP is replaced</strong> (the matrix levels aside, which
          this app cannot write yet). The outputs are muted while it is written; the outputs in
          use come back on at the end, <strong>the inputs stay muted</strong>. Then the setup is
          stored to {label(draft.slot)}, replacing "{slotName}".
        </p>
        <div class="actions">
          <button class="primary" disabled={busy} onclick={apply}
            >{busy ? "Writing…" : "Write and store"}</button
          >
          <button disabled={busy} onclick={() => (confirming = false)}>Cancel</button>
        </div>
      </div>
    {:else}
      <div class="actions">
        <button
          class="primary"
          disabled={app.readOnly || errors.length > 0}
          onclick={() => (confirming = true)}>Write to the DSP…</button
        >
      </div>
      {#if app.readOnly}
        <p class="muted note">Read-only: take Control (or connect the DSP) to write the setup.</p>
      {/if}
    {/if}
  </section>
{/if}

<style>
  .hint {
    font-size: 0.85rem;
    margin: 0 0 10px;
  }
  .ways {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(min(280px, 100%), 1fr));
    gap: 8px;
  }
  .way {
    padding: 10px;
    border-radius: 8px;
    background: var(--panel-2);
  }
  h3 {
    font-size: 1rem;
    margin: 0 0 6px;
  }
  h3 small {
    color: var(--muted);
    font-weight: 400;
    font-size: 0.8rem;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 2px 10px;
    margin: 0 0 8px;
    font-size: 0.85rem;
    font-variant-numeric: tabular-nums;
  }
  dt {
    color: var(--muted);
  }
  dd {
    margin: 0;
    text-align: right;
    min-width: 0;
  }
  dd.nowrap {
    white-space: nowrap;
  }
  .gain {
    display: grid;
    grid-template-columns: 1fr 6em auto;
    align-items: center;
    gap: 8px;
  }
  .gain input {
    text-align: right;
  }
  small {
    color: var(--muted);
    font-size: 0.75rem;
  }
  .note {
    margin: 8px 0 0;
    font-size: 0.8rem;
  }
  .inputs {
    margin: 0;
    padding-left: 18px;
    font-size: 0.9rem;
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
  .store {
    display: grid;
    gap: 8px;
    max-width: 420px;
  }
  .store label {
    display: grid;
    gap: 4px;
  }
  .store span {
    color: var(--muted);
    font-size: 0.85rem;
  }
  .warn {
    color: var(--warn);
    margin: 8px 0 0;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 10px;
  }
  .confirm {
    margin-top: 10px;
    padding: 10px;
    border-radius: 8px;
    background: var(--panel-2);
    border: 1px solid var(--warn);
  }
  .confirm p {
    margin: 0;
    font-size: 0.9rem;
  }
  .done p {
    margin: 0 0 8px;
  }
</style>
