<script lang="ts">
  import { app } from "../lib/app.svelte";
  import { nav, slotLabel } from "../lib/nav.svelte";
  import { formatDb, meterPos } from "../lib/scale";
  import type { InputChannel, OutputChannel } from "../lib/types";
  import CrossoverSection from "./CrossoverSection.svelte";
  import DynamicsSection from "./DynamicsSection.svelte";
  import Field from "./Field.svelte";
  import GeqSection from "./GeqSection.svelte";
  import PeqSection from "./PeqSection.svelte";
  import Section from "./Section.svelte";

  interface Props {
    path: string; // "inputs.0" / "outputs.3"
  }

  let { path }: Props = $props();

  const isOutput = $derived(path.startsWith("outputs."));
  const index = $derived(Number(path.split(".")[1]));
  const device = $derived(app.device);
  const input = $derived(isOutput ? undefined : (device?.inputs[index] as InputChannel | undefined));
  const output = $derived(isOutput ? (device?.outputs[index] as OutputChannel | undefined) : undefined);
  const channel = $derived(input ?? output);

  const paths = $derived([
    ...(device?.inputs ?? []).map((_, i) => `inputs.${i}`),
    ...(device?.outputs ?? []).map((_, i) => `outputs.${i}`),
  ]);
  const position = $derived(paths.indexOf(path));
  const previous = $derived(position > 0 ? paths[position - 1] : undefined);
  const next = $derived(position >= 0 && position < paths.length - 1 ? paths[position + 1] : undefined);

  // Live level of this channel.
  const inputCount = $derived(app.hello?.profile.input_count ?? 4);
  const meterIndex = $derived(isOutput ? inputCount + index : index);
  const level = $derived(app.meters?.levels?.[meterIndex] ?? null);
  const clip = $derived(app.meters?.clip?.[meterIndex] ?? false);
  const limit = $derived(isOutput ? (app.meters?.limit?.[index] ?? null) : null);
  const comp = $derived(isOutput ? (app.meters?.comp?.[index] ?? null) : null);
  const floor = $derived(app.hello?.profile.meter_floor_db ?? -90);
  const limits = $derived(app.hello?.limits);

  // Channel name editing.
  let nameDraft = $state("");
  let nameFocused = $state(false);
  const nameLength = $derived(limits?.channel_name_length ?? 8);
  const nameValid = $derived(/^[\x20-\x7e]*$/.test(nameDraft) && nameDraft.length <= nameLength);
  $effect(() => {
    // Follow the device's name unless the user is typing.
    const name = channel?.name ?? "";
    if (!nameFocused) nameDraft = name;
  });

  async function saveName(event?: SubmitEvent) {
    event?.preventDefault();
    if (!channel || !nameValid || nameDraft === channel.name) return;
    await app.set(`${path}.name`, nameDraft);
    (document.activeElement as HTMLElement | null)?.blur();
  }

  function onKey(event: KeyboardEvent) {
    if (event.key === "Escape" && !(event.target instanceof HTMLInputElement)) nav.close();
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="detail">
  <header class="bar">
    <button class="back" onclick={() => nav.close()} aria-label="Back to the mixer">‹ Mixer</button>
    <button
      class="nav"
      disabled={!previous}
      onclick={() => previous && nav.open(previous)}
      aria-label="Previous channel">‹</button
    >
    <div class="name">
      <strong>{slotLabel(path)}</strong>
      {#if channel?.name}<span class="muted">{channel.name}</span>{/if}
    </div>
    <button
      class="nav"
      disabled={!next}
      onclick={() => next && nav.open(next)}
      aria-label="Next channel">›</button
    >
  </header>

  {#if !channel}
    <p class="muted">No such channel.</p>
  {:else}
    <div class="meter" aria-label="Level">
      <div class="level" class:clip style:width={`${meterPos(level, floor) * 100}%`}></div>
      <span class="db">{level === null ? "—" : `${formatDb(level)} dB`}</span>
      {#if clip}<span class="led clip">CLIP</span>{/if}
      {#if limit !== null}<span class="led" class:on={limit}>LIM</span>{/if}
      {#if comp !== null}<span class="led" class:on={comp}>COMP</span>{/if}
    </div>

    <div class="sections">
      <Section id="channel" title="Channel">
        {#if limits}
          <Field
            label="Gain"
            value={channel.gain_db}
            min={limits.gain_db[0]}
            max={limits.gain_db[1]}
            unit="dB"
            step={0.5}
            resolution={0.1}
            origin={0}
            format={(v) => formatDb(v)}
            disabled={!app.editable("gain_db")}
            onchange={(v) => app.set(`${path}.gain_db`, v)}
          />
        {/if}
        <div class="toggles">
          <button
            class="switch danger"
            class:on={channel.mute}
            disabled={!app.editable("mute")}
            aria-pressed={channel.mute}
            onclick={() => app.set(`${path}.mute`, !channel.mute)}>Mute</button
          >
          <button
            class="switch"
            class:on={channel.phase}
            disabled={!app.editable("phase")}
            aria-pressed={channel.phase}
            title="Phase invert"
            onclick={() => app.set(`${path}.phase`, !channel.phase)}>Ø Phase</button
          >
        </div>
        <form class="rename" onsubmit={saveName}>
          <label for="channel-name" class="muted">Name</label>
          <input
            id="channel-name"
            type="text"
            maxlength={nameLength}
            autocomplete="off"
            enterkeyhint="done"
            bind:value={nameDraft}
            class:invalid={!nameValid}
            disabled={!app.editable("name")}
            onfocus={() => (nameFocused = true)}
            onblur={() => {
              nameFocused = false;
              void saveName();
            }}
          />
          <button
            type="submit"
            disabled={!app.editable("name") || !nameValid || nameDraft === channel.name}>Save</button
          >
        </form>
        <p class="hint muted">
          {nameLength} characters max, plain ASCII.
          {#if !app.verified("name")}Name changes are not verified on a real DSP 408 yet.{/if}
        </p>
      </Section>

      {#if output && limits}
        {@const c = limits.speed_of_sound_m_s}
        <Section id="delay" title="Delay" kind="delay_ms">
          <Field
            label="Delay"
            value={output.delay_ms}
            min={0}
            max={app.hello?.profile.delay_max_ms ?? 680}
            unit="ms"
            scale="sqrt"
            step={0.1}
            resolution={0.01}
            digits={2}
            disabled={!app.editable("delay_ms")}
            onchange={(v) => app.set(`${path}.delay_ms`, v)}
          />
          <Field
            label="Distance"
            value={(output.delay_ms * c) / 1000}
            min={0}
            max={((app.hello?.profile.delay_max_ms ?? 680) * c) / 1000}
            unit="m"
            step={0.1}
            resolution={0.01}
            digits={2}
            slider={false}
            disabled={!app.editable("delay_ms")}
            onchange={(m) => app.set(`${path}.delay_ms`, (m * 1000) / c)}
          />
        </Section>
        <CrossoverSection channel={output} {path} />
      {/if}

      <PeqSection {channel} {path} />

      {#if output}
        <DynamicsSection kind="compressor" {path} values={{ ...output.compressor }} reduction={comp} />
        <DynamicsSection kind="limiter" {path} values={{ ...output.limiter }} reduction={limit} />
      {/if}

      {#if input}
        <DynamicsSection kind="gate" {path} values={{ ...input.gate }} />
        <GeqSection channel={input} {path} />
      {/if}
    </div>
  {/if}
</div>

<style>
  .detail {
    max-width: 1200px;
    margin: 0 auto;
  }
  .bar {
    position: sticky;
    top: -12px;
    z-index: 2;
    display: grid;
    grid-template-columns: auto 44px 1fr 44px;
    align-items: center;
    gap: 6px;
    margin: -12px -12px 10px;
    padding: 8px 12px;
    background: var(--bg);
    border-bottom: 1px solid var(--line);
  }
  .back {
    padding: 0 12px;
  }
  .nav {
    padding: 0;
    font-size: 1.3rem;
  }
  .name {
    display: flex;
    align-items: baseline;
    justify-content: center;
    gap: 8px;
    min-width: 0;
    white-space: nowrap;
    overflow: hidden;
  }
  .meter {
    position: relative;
    display: flex;
    align-items: center;
    gap: 6px;
    height: 28px;
    margin-bottom: 10px;
    padding: 0 8px;
    border-radius: 6px;
    background: #0b0c0f;
    overflow: hidden;
  }
  .level {
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    background: linear-gradient(90deg, #1f8f5f, var(--accent) 70%, var(--warn) 88%, var(--danger));
    opacity: 0.6;
    transition: width 0.12s linear;
  }
  .level.clip {
    background: var(--danger);
  }
  .db {
    position: relative;
    flex: 1;
    font-variant-numeric: tabular-nums;
    font-size: 0.85rem;
  }
  .led {
    position: relative;
    font-size: 0.7rem;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    background: var(--panel-2);
    color: var(--muted);
  }
  .led.on {
    background: var(--warn);
    color: #000;
  }
  .led.clip {
    background: var(--danger);
    color: #fff;
  }
  .sections {
    columns: 2 420px;
    column-gap: 10px;
  }
  .toggles {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin: 8px 0;
  }
  .rename {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 8px;
  }
  .rename input {
    min-height: 40px;
  }
  .rename input.invalid {
    border-color: var(--danger);
  }
  .hint {
    font-size: 0.8rem;
    margin: 6px 0 0;
  }
</style>
