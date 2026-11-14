<script lang="ts">
  // Setup wizard, step 3: per way, the speaker's specs, how the cabinets are wired to the
  // amplifier, the amplifier (gain or sensitivity, power at that load) and the limiter.
  import { formatDb } from "../lib/scale";
  import {
    amplifier,
    AMPLIFIERS,
    ampGain,
    ampPowerAt,
    librarySection,
    load,
    refreshAmpPower,
    useAmplifier,
    wayLevel,
    type Way,
  } from "../lib/setup";
  import { wizard } from "../lib/wizard.svelte";

  const draft = $derived(wizard.draft);

  function ampChoice(way: Way): string {
    return way.amp.active ? "active" : (way.amp.ref ?? "other");
  }

  function chooseAmp(way: Way, value: string) {
    if (value === "active") {
      way.amp.active = true;
      way.amp.ref = null;
    } else if (value === "other") {
      way.amp.active = false;
      way.amp.ref = null;
    } else {
      useAmplifier(way, amplifier(value));
    }
  }

  const ohms = (z: number) => `${Number(z.toFixed(2))} Ω`;
  const dbu = (v: number) => `${formatDb(v)} dBu`;
</script>

{#each draft.ways as way (way.id)}
  {@const section = librarySection(way.speaker.ref)}
  {@const estimated = new Set(section?.estimated ?? [])}
  {@const l = load(way)}
  {@const level = wayLevel(way)}
  {@const amp = amplifier(way.amp.ref)}
  <section class="card way">
    <h2>{way.name} <small>{way.speaker.label}</small></h2>

    <h3>Speaker <small>one cabinet</small></h3>
    <div class="fields">
      <label>
        <span>Range, bottom</span>
        <input type="text" inputmode="decimal" bind:value={way.speaker.lowHz} />
        <small>Hz</small>
      </label>
      <label>
        <span>Range, top</span>
        <input type="text" inputmode="decimal" bind:value={way.speaker.highHz} />
        <small>Hz</small>
      </label>
      <label>
        <span>Power{#if estimated.has("aes_w")}<em class="est">estimated</em>{/if}</span>
        <input type="text" inputmode="decimal" bind:value={way.speaker.aesW} />
        <small>W AES</small>
      </label>
      <label>
        <span>Impedance</span>
        <input
          type="text"
          inputmode="decimal"
          bind:value={way.speaker.impedanceOhm}
          onchange={() => refreshAmpPower(way)}
        />
        <small>Ω</small>
      </label>
      <label>
        <span
          >Sensitivity{#if estimated.has("sensitivity_db")}<em class="est">estimated</em>{/if}</span
        >
        <input type="text" inputmode="decimal" bind:value={way.speaker.sensitivityDb} />
        <small>dB 1 W/1 m</small>
      </label>
      <div class="pair">
        <span>Load</span>
        <div class="seg" role="group" aria-label="Load">
          <button class:on={way.speaker.load === "open"} onclick={() => (way.speaker.load = "open")}
            >Open</button
          >
          <button
            class:on={way.speaker.load === "closed"}
            onclick={() => (way.speaker.load = "closed")}>Closed</button
          >
        </div>
      </div>
    </div>
    {#if section}<p class="source muted">{section.drivers}. {section.source}</p>{/if}

    <h3>Wiring</h3>
    <div class="fields">
      <label>
        <span>Cabinets per amplifier channel</span>
        <input
          type="number"
          min="1"
          max="16"
          bind:value={way.cabinets}
          onchange={() => refreshAmpPower(way)}
        />
        <small></small>
      </label>
      {#if way.cabinets > 1}
        <div class="pair">
          <span>Wired in</span>
          <div class="seg" role="group" aria-label="Wiring">
            <button
              class:on={way.wiring === "parallel"}
              onclick={() => {
                way.wiring = "parallel";
                refreshAmpPower(way);
              }}>Parallel</button
            >
            <button
              class:on={way.wiring === "series"}
              onclick={() => {
                way.wiring = "series";
                refreshAmpPower(way);
              }}>Series</button
            >
          </div>
        </div>
      {/if}
      <label>
        <span>Amplifier channels per output{way.stereo ? " (each side)" : ""}</span>
        <input type="number" min="1" max="16" bind:value={way.ampChannels} />
        <small></small>
      </label>
    </div>
    {#if l}
      <p class="muted derived">
        On one amplifier channel: {ohms(l.impedanceOhm)}, {Math.round(l.aesW)} W AES.
      </p>
    {/if}

    <h3>Amplifier</h3>
    <select
      aria-label="Amplifier"
      value={ampChoice(way)}
      onchange={(e) => chooseAmp(way, e.currentTarget.value)}
    >
      {#each AMPLIFIERS as a (a.id)}
        <option value={a.id}>{a.name} ({a.channels} channels)</option>
      {/each}
      <option value="other">Other amplifier (typed in)</option>
      <option value="active">Active speakers (no amplifier, no limiter)</option>
    </select>
    {#if !way.amp.active}
      <div class="fields">
        <div class="pair">
          <span>Given as</span>
          <div class="seg" role="group" aria-label="Gain or sensitivity">
            <button
              class:on={way.amp.gainMode === "gain"}
              onclick={() => (way.amp.gainMode = "gain")}>Gain</button
            >
            <button
              class:on={way.amp.gainMode === "sensitivity"}
              onclick={() => (way.amp.gainMode = "sensitivity")}>Sensitivity</button
            >
          </div>
        </div>
        {#if way.amp.gainMode === "gain"}
          <label>
            <span>Gain</span>
            <input type="text" inputmode="decimal" bind:value={way.amp.gainDb} />
            <small>dB</small>
          </label>
          {#if amp}
            <p class="muted note">
              Datasheet: {amp.gains_db.join(" · ")} dB. Enter the real gain of the position you
              use if you know it (it can differ, e.g. 40.5 dB for "41 dB").
            </p>
          {/if}
        {:else}
          <label>
            <span>Input sensitivity</span>
            <input type="text" inputmode="decimal" bind:value={way.amp.sensitivityV} />
            <small>V</small>
          </label>
          <label>
            <span>for a power of</span>
            <input type="text" inputmode="decimal" bind:value={way.amp.sensitivityPowerW} />
            <small>W</small>
          </label>
          <label>
            <span>into</span>
            <input type="text" inputmode="decimal" bind:value={way.amp.sensitivityOhm} />
            <small>Ω</small>
          </label>
          {#if Number.isFinite(ampGain(way))}
            <p class="muted note">That is a gain of {ampGain(way).toFixed(1)} dB.</p>
          {/if}
        {/if}
        <label>
          <span>Power {l ? `into ${ohms(l.impedanceOhm)}` : "at this load"} <em>(optional)</em></span>
          <input type="text" inputmode="decimal" bind:value={way.amp.powerW} placeholder="—" />
          <small>W</small>
        </label>
        {#if amp && l && ampPowerAt(amp, l.impedanceOhm) === null}
          <p class="warn note">{ohms(l.impedanceOhm)} is below the lowest load {amp.name} is rated for.</p>
        {/if}
      </div>

      <h3>Limiter</h3>
      <div class="fields">
        <div class="pair">
          <span>Threshold</span>
          <div class="seg" role="group" aria-label="Hard or soft">
            <button class:on={way.mode === "hard"} onclick={() => (way.mode = "hard")}>Hard</button>
            <button class:on={way.mode === "soft"} onclick={() => (way.mode = "soft")}
              >Soft +2</button
            >
          </div>
        </div>
        <div class="pair">
          <span>0.5 dB step</span>
          <div class="seg" role="group" aria-label="Rounding">
            <button class:on={way.rounding === "up"} onclick={() => (way.rounding = "up")}>Up</button>
            <button class:on={way.rounding === "down"} onclick={() => (way.rounding = "down")}
              >Down</button
            >
          </div>
        </div>
      </div>
      {#if level.limiter}
        <dl class="result">
          <dt>Compressor (ratio Limit)</dt>
          <dd>{dbu(level.limiter.compThresholdDbu)}</dd>
          <dt>Limiter</dt>
          <dd>{dbu(level.limiter.limitThresholdDbu)}</dd>
          <dt>Limited by</dt>
          <dd>{level.limiter.limitedBy === "amp" ? "the amplifier (half power)" : "the speaker"}</dd>
          {#if level.splMaxDb !== null}
            <dt>SPL at the threshold</dt>
            <dd>{level.splMaxDb.toFixed(1)} dB at 1 m</dd>
          {/if}
        </dl>
        {#if level.limiter.clamped}
          <p class="warn note">Outside the DSP's threshold range (−90 … +20 dBu): clamped.</p>
        {/if}
      {/if}
    {:else}
      <p class="muted note">
        Active speakers protect themselves: no compressor or limiter, output gain 0 dB.
      </p>
    {/if}
  </section>
{/each}

<style>
  .way {
    display: grid;
    gap: 6px;
  }
  h2 small {
    color: var(--muted);
    font-weight: 400;
    font-size: 0.85rem;
  }
  h3 {
    font-size: 0.95rem;
    margin: 10px 0 2px;
  }
  h3 small {
    color: var(--muted);
    font-weight: 400;
  }
  .fields {
    display: grid;
    gap: 6px;
    max-width: 460px;
  }
  .fields label,
  .pair {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 5.4em 4.6em;
    align-items: center;
    gap: 8px;
  }
  .pair .seg {
    grid-column: 2 / -1;
    min-width: 0;
  }
  .pair .seg button {
    flex: 1;
    padding: 0 4px;
    white-space: nowrap;
  }
  .fields input {
    text-align: right;
  }
  input[type="number"] {
    min-height: var(--tap);
    padding: 0 8px;
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: var(--bg);
    width: 100%;
  }
  small {
    color: var(--muted);
    font-size: 0.75rem;
  }
  em {
    color: var(--muted);
    font-style: normal;
    font-size: 0.8rem;
  }
  .est {
    margin-left: 6px;
    color: var(--warn);
  }
  .source,
  .derived,
  .note {
    margin: 0;
    font-size: 0.8rem;
  }
  .warn {
    color: var(--warn);
  }
  select {
    max-width: 460px;
  }
  .result {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 4px 12px;
    margin: 6px 0 0;
    max-width: 460px;
    font-variant-numeric: tabular-nums;
  }
  .result dt {
    color: var(--muted);
  }
  .result dd {
    margin: 0;
    text-align: right;
    font-weight: 600;
  }
</style>
