<script lang="ts">
  // One channel of the Live view: big CLIP / CMP / LIM indicators, a graduated meter with the
  // dynamics thresholds, the gain fader with − / +, and MUTE.
  import { app } from "../lib/app.svelte";
  import { METER_COLORS } from "../lib/scale";
  import { nav, slotLabel } from "../lib/nav.svelte";
  import type { InputChannel, OutputChannel } from "../lib/types";
  import BigMeter, { LIMIT_COLOR } from "./BigMeter.svelte";
  import Fader from "./Fader.svelte";

  interface Props {
    path: string; // "inputs.0" / "outputs.3"
  }

  let { path }: Props = $props();

  const CLIP_LATCH_MS = 2000;

  const isOutput = $derived(path.startsWith("outputs."));
  const index = $derived(Number(path.split(".")[1]));
  const input = $derived(
    isOutput ? undefined : (app.device?.inputs[index] as InputChannel | undefined),
  );
  const output = $derived(
    isOutput ? (app.device?.outputs[index] as OutputChannel | undefined) : undefined,
  );
  const channel = $derived(input ?? output);
  const meterIndex = $derived(isOutput ? (app.hello?.profile.input_count ?? 4) + index : index);
  const level = $derived(app.meters?.levels?.[meterIndex] ?? null);
  const clipNow = $derived(app.meters?.clip?.[meterIndex] ?? false);
  const comp = $derived(isOutput ? (app.meters?.comp?.[index] ?? false) : false);
  const limit = $derived(isOutput ? (app.meters?.limit?.[index] ?? false) : false);

  // CLIP stays lit for 2 s so that a short overload is seen.
  let clipUntil = $state(0);
  let now = $state(0);
  $effect(() => {
    now = performance.now();
    if (clipNow) clipUntil = now + CLIP_LATCH_MS;
  });
  $effect(() => {
    if (clipUntil <= now) return;
    const timer = setTimeout(() => (now = performance.now()), clipUntil - now + 10);
    return () => clearTimeout(timer);
  });
  const clip = $derived(clipNow || clipUntil > now);
</script>

{#if channel}
  <section class="strip" class:muted={channel.mute} style:--ch={app.color(path)}>
    <button class="name" onclick={() => nav.open(path)} title="Open this channel">
      <span class="slot">{slotLabel(path)}{channel.linked.length ? " 🔗" : ""}</span>
      <strong>{channel.name || "—"}</strong>
    </button>

    <div class="leds">
      <span class="led" class:on={clip} style:--c="var(--danger)">CLIP</span>
      {#if output}
        <span class="led" class:on={comp} style:--c={METER_COLORS.orange}>CMP</span>
        <span class="led" class:on={limit} style:--c={LIMIT_COLOR}>LIM</span>
      {/if}
    </div>

    <div class="body">
      <BigMeter
        {level}
        {clip}
        compThreshold={output && output.compressor.ratio > 0 ? output.compressor.threshold_db : null}
        limitThreshold={output ? output.limiter.threshold_db : null}
      />
      <Fader
        value={channel.gain_db}
        label={channel.name}
        disabled={!app.editable("gain_db")}
        onchange={(db) => app.set(`${path}.gain_db`, db)}
      />
    </div>

    <button
      class="mute"
      class:on={channel.mute}
      disabled={!app.editable("mute")}
      aria-pressed={channel.mute}
      onclick={() => app.set(`${path}.mute`, !channel.mute)}>MUTE</button
    >
  </section>
{/if}

<style>
  .strip {
    flex: 0 0 132px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 8px 6px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    min-height: 0;
  }
  .name {
    border: 2px solid var(--ch);
    color: var(--ch);
    display: grid;
    min-height: 40px;
    padding: 2px 4px;
    line-height: 1.15;
    min-width: 0;
  }
  .name span,
  .name strong {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .slot {
    font-size: 0.7rem;
    color: inherit;
  }
  .strip.muted {
    /* Muted: a thick red frame and a reddened background (the name keeps its channel colour,
       which can itself be red). An inset shadow, so the strip keeps its size. */
    border-color: var(--danger);
    box-shadow: inset 0 0 0 2px var(--danger);
    background: color-mix(in srgb, var(--danger) 14%, var(--panel));
  }
  .leds {
    display: grid;
    grid-auto-flow: column;
    grid-auto-columns: 1fr;
    gap: 4px;
  }
  .led {
    display: grid;
    place-items: center;
    height: 30px;
    border-radius: 6px;
    font-size: 0.72rem;
    font-weight: 800;
    letter-spacing: 0.02em;
    background: var(--panel-2);
    color: var(--muted);
    border: 1px solid var(--line);
  }
  .led.on {
    background: var(--c);
    border-color: var(--c);
    color: #000;
    box-shadow: 0 0 10px var(--c);
  }
  .body {
    flex: 1;
    display: flex;
    justify-content: center;
    gap: 6px;
    min-height: 0;
  }
  .mute {
    min-height: 52px;
    font-weight: 800;
    font-size: 0.95rem;
  }
  .mute.on {
    background: var(--danger);
    border-color: var(--danger);
    color: #fff;
  }
</style>
