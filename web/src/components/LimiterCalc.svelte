<script lang="ts">
  // "Limiter" tab: compute the compressor / limiter thresholds that protect a speaker, from the
  // amp gain, the speaker power, the load and impedance (Hornplans method), then apply them.
  import { app } from "../lib/app.svelte";
  import { links } from "../lib/links.svelte";
  import {
    APPLIED,
    computeLimiter,
    LIMITER_ABOVE_COMP_DB,
    type LimiterInput,
    type Load,
    type Mode,
    type Rounding,
    validate,
  } from "../lib/limiter";
  import { formatDb } from "../lib/scale";

  const STORAGE_KEY = "dsp408.limiter.calc";

  interface Form {
    speakerAesW: string;
    impedanceOhm: string;
    ampGainDb: string;
    ampPowerW: string;
    load: Load;
    mode: Mode;
    rounding: Rounding;
  }

  function load(): Form {
    const fallback: Form = {
      speakerAesW: "",
      impedanceOhm: "8",
      ampGainDb: "",
      ampPowerW: "",
      load: "open",
      mode: "hard",
      rounding: "down",
    };
    try {
      return { ...fallback, ...(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}") as Form) };
    } catch {
      return fallback;
    }
  }

  let form = $state<Form>(load());
  $effect(() => {
    const snapshot = JSON.stringify(form);
    try {
      localStorage.setItem(STORAGE_KEY, snapshot);
    } catch {
      // not persisted: fine
    }
  });

  const num = (text: string) => (text.trim() === "" ? NaN : Number(text.replace(",", ".")));

  const input = $derived<LimiterInput>({
    speakerAesW: num(form.speakerAesW),
    impedanceOhm: num(form.impedanceOhm),
    ampGainDb: num(form.ampGainDb),
    ampPowerW: form.ampPowerW.trim() === "" ? null : num(form.ampPowerW),
    load: form.load,
    mode: form.mode,
    rounding: form.rounding,
  });
  const error = $derived(validate(input));
  const result = $derived(error ? null : computeLimiter(input));

  // --- applying ------------------------------------------------------------------------------
  const outputs = $derived(app.device?.outputs ?? []);
  const limitRatio = $derived(
    Math.max(0, (app.hello?.profile.ratios ?? []).findIndex((r) => /limit/i.test(r))),
  );
  const editable = $derived(app.editable("compressor") && app.editable("limiter"));
  let selected = $state<number[]>([]);
  let confirming = $state(false);
  let busy = $state(false);

  function toggle(i: number) {
    confirming = false;
    selected = selected.includes(i) ? selected.filter((n) => n !== i) : [...selected, i].sort();
  }

  async function apply() {
    if (!result) return;
    busy = true;
    let ok = true;
    for (const i of selected) {
      ok =
        (await app.set(`outputs.${i}.compressor`, {
          ...APPLIED.compressor,
          ratio: limitRatio,
          threshold_db: result.compThresholdDbu,
        })) && ok;
      ok =
        (await app.set(`outputs.${i}.limiter`, {
          ...APPLIED.limiter,
          threshold_db: result.limitThresholdDbu,
        })) && ok;
    }
    busy = false;
    confirming = false;
    if (ok) {
      app.toast(`Applied to ${selected.map((i) => links.slot(`outputs.${i}`)).join(", ")}`);
      selected = [];
    }
  }

  const dbu = (v: number) => `${formatDb(v)} dBu`;
</script>

<div class="calc">
  <section class="card">
    <h2>Limiter calculator</h2>
    <div class="fields">
      <label>
        <span>Amplifier gain</span>
        <input type="text" inputmode="decimal" bind:value={form.ampGainDb} placeholder="32" />
        <small>dB</small>
      </label>
      <label>
        <span>Speaker power</span>
        <input type="text" inputmode="decimal" bind:value={form.speakerAesW} placeholder="1600" />
        <small>W AES</small>
      </label>
      <label>
        <span>Impedance</span>
        <input type="text" inputmode="decimal" bind:value={form.impedanceOhm} placeholder="8" />
        <small>Ω</small>
      </label>
      <label>
        <span>Amplifier power <em>(optional)</em></span>
        <input type="text" inputmode="decimal" bind:value={form.ampPowerW} placeholder="—" />
        <small>W RMS</small>
      </label>
    </div>
    <p class="hint muted">
      Totals for one amplifier channel: all the speakers wired to it (power and impedance), and the
      amplifier's power at that impedance. With the amplifier power, the threshold also keeps the
      amplifier below half its power (−3 dB) so that it does not clip.
    </p>

    <fieldset>
      <legend>Load</legend>
      <label class="choice"
        ><input type="radio" bind:group={form.load} value="open" /> Open
        <small>horn, vented box: speaker at AES / 1.56 (−1.9 dB)</small></label
      >
      <label class="choice"
        ><input type="radio" bind:group={form.load} value="closed" /> Closed
        <small>sealed box: AES / 2.34 (−3.7 dB)</small></label
      >
    </fieldset>
    <fieldset>
      <legend>Limiter</legend>
      <label class="choice"
        ><input type="radio" bind:group={form.mode} value="hard" /> Hard
        <small>Hornplans' threshold (the load factor keeps the speaker under its AES power)</small
        ></label
      >
      <label class="choice"
        ><input type="radio" bind:group={form.mode} value="soft" /> Soft
        <small>2 dB higher</small></label
      >
    </fieldset>
    <fieldset>
      <legend>Rounding to the DSP step (0.5 dB)</legend>
      <label class="choice"
        ><input type="radio" bind:group={form.rounding} value="down" /> Down
        <small>never above the computed threshold (safe side)</small></label
      >
      <label class="choice"
        ><input type="radio" bind:group={form.rounding} value="up" /> Up
        <small>up to 0.5 dB above the computed threshold</small></label
      >
    </fieldset>
  </section>

  <section class="card result">
    <h2>Result</h2>
    {#if error || !result}
      <p class="muted">{error}</p>
    {:else}
      <dl>
        <dt>Speaker limit</dt>
        <dd class:lowest={result.limitedBy === "speaker"}>{dbu(result.speakerDbu)}</dd>
        {#if result.ampDbu !== null}
          <dt>Amplifier limit</dt>
          <dd class:lowest={result.limitedBy === "amp"}>{dbu(result.ampDbu)}</dd>
        {/if}
        <dt>Hard threshold (Hornplans)</dt>
        <dd>{dbu(result.hornplansDbu)}</dd>
        {#if form.mode === "soft"}
          <dt>Soft threshold (+{result.extraDb} dB)</dt>
          <dd>{dbu(result.thresholdDbu)}</dd>
        {/if}
        <dt>DSP step (0.5 dB, rounded {result.rounding})</dt>
        <dd>{dbu(result.compThresholdDbu)}</dd>
      </dl>
      <div class="big">
        <div>
          <span>Compressor</span>
          <strong>{dbu(result.compThresholdDbu)}</strong>
          <small>ratio Limit · attack 1 ms · release 1000 ms · knee 0</small>
        </div>
        <div>
          <span>Limiter</span>
          <strong>{dbu(result.limitThresholdDbu)}</strong>
          <small>compressor +{LIMITER_ABOVE_COMP_DB} dB · attack 1 ms · release 1000 ms</small>
        </div>
      </div>
      {#if result.clamped}
        <p class="warn">Outside the DSP's threshold range (−90 … +20 dBu): clamped.</p>
      {/if}

      <h3>Apply to</h3>
      <div class="chips" role="group" aria-label="Outputs">
        {#each outputs as ch, i (i)}
          <!-- One chip per link group when merging: the DSP applies the change to the group. -->
          {#if links.isShown(`outputs.${i}`)}
          <button
            class="ch-bar"
            style:--ch={app.color(`outputs.${i}`)}
            class:on={selected.includes(i)}
            aria-pressed={selected.includes(i)}
            disabled={!editable || busy}
            onclick={() => toggle(i)}
          >
            <span>{links.slot(`outputs.${i}`)}{links.mark(`outputs.${i}`)}</span>
            <small>{links.name(`outputs.${i}`)}</small>
            <small class="now"
              >C {formatDb(ch.compressor.threshold_db)} · L {formatDb(ch.limiter.threshold_db)}</small
            >
          </button>
          {/if}
        {/each}
      </div>
      {#if confirming}
        <div class="confirm">
          <p>
            {selected.map((i) => links.slot(`outputs.${i}`)).join(", ")}: compressor
            <strong>{dbu(result.compThresholdDbu)}</strong>, ratio Limit, attack 1 ms, release
            1000 ms, knee 0; limiter <strong>{dbu(result.limitThresholdDbu)}</strong>, attack 1 ms,
            release 1000 ms. Linked outputs follow (the DSP copies the change).
          </p>
          <div class="actions">
            <button class="primary" disabled={busy} onclick={apply}>Apply</button>
            <button disabled={busy} onclick={() => (confirming = false)}>Cancel</button>
          </div>
        </div>
      {:else}
        <div class="actions">
          <button
            class="primary"
            disabled={!editable || busy || selected.length === 0}
            onclick={() => (confirming = true)}>Apply to selected</button
          >
        </div>
      {/if}
    {/if}
  </section>

  <p class="muted hint source">
    Method: Marc.O's limiter calculator (hornplans.free.fr), dBu mode, for an RMS limiter. A
    limiter with a long attack lets more peaks through: lower the threshold then. Any audible
    distortion means something is wrong.
  </p>
</div>

<style>
  .calc {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 10px;
    align-items: start;
  }
  .fields {
    display: grid;
    gap: 8px;
  }
  .fields label {
    display: grid;
    grid-template-columns: 1fr 7em 3.6em;
    align-items: center;
    gap: 8px;
  }
  .fields em {
    color: var(--muted);
    font-style: normal;
    font-size: 0.8rem;
  }
  .fields input {
    text-align: right;
  }
  small {
    color: var(--muted);
    font-size: 0.75rem;
  }
  .hint {
    font-size: 0.8rem;
    margin: 10px 0;
  }
  fieldset {
    border: 1px solid var(--line);
    border-radius: 8px;
    margin: 8px 0 0;
    padding: 6px 10px 8px;
  }
  legend {
    color: var(--muted);
    font-size: 0.85rem;
  }
  .choice {
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: 36px;
  }
  .choice input {
    flex: none; /* a long description must not shrink the radio */
    width: 20px;
    height: 20px;
  }
  dl {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 4px 12px;
    margin: 0 0 12px;
    font-variant-numeric: tabular-nums;
  }
  dt {
    color: var(--muted);
  }
  dd {
    margin: 0;
    text-align: right;
  }
  dd.lowest {
    color: var(--accent);
    font-weight: 700;
  }
  .big {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .big div {
    display: grid;
    gap: 2px;
    padding: 10px;
    border-radius: 8px;
    background: var(--panel-2);
  }
  .big strong {
    font-size: 1.5rem;
    font-variant-numeric: tabular-nums;
  }
  .warn {
    color: var(--warn);
  }
  h3 {
    font-size: 1rem;
    margin: 16px 0 8px;
  }
  .chips {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
  }
  .chips button {
    display: grid;
    padding: 6px 4px;
    line-height: 1.15;
    min-width: 0;
  }
  .chips small {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .chips .now {
    font-size: 0.65rem;
  }
  .chips .ch-bar:not(.on) {
    border-color: color-mix(in srgb, var(--ch) 60%, var(--line));
  }
  .chips .ch-bar span,
  .chips .ch-bar small:not(.now) {
    color: var(--ch);
  }
  .chips .on {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
    background: color-mix(in srgb, var(--accent) 18%, var(--panel-2));
  }
  .actions {
    display: flex;
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
  .source {
    grid-column: 1 / -1;
  }
</style>
