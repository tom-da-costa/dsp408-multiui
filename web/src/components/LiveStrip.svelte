<script lang="ts">
  // One channel of the Live view: big CLIP / CMP / LIM indicators, a graduated meter with the
  // dynamics thresholds, the gain fader with − / +, SIG (signal present) and MUTE.
  import { app } from "../lib/app.svelte";
  import { links } from "../lib/links.svelte";
  import { COMP_COLOR, LIMIT_COLOR } from "../lib/scale";
  import { nav } from "../lib/nav.svelte";
  import { SIGNAL_COLOR, signalLit } from "../lib/signal.svelte";
  import type { InputChannel, OutputChannel } from "../lib/types";
  import BigMeter from "./BigMeter.svelte";
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
  // Merged over the link group when "Merge linked channels" is on.
  const meter = $derived(links.meter(path));
  const level = $derived(meter.level);
  const clipNow = $derived(meter.clip);
  const comp = $derived(meter.comp ?? false);
  const limit = $derived(meter.limit ?? false);

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
  const sig = signalLit(() => level);
</script>

{#if channel}
  <section class="strip" class:muted={channel.mute} style:--ch={app.color(path)}>
    <button class="name" onclick={() => nav.open(path)} title="Open this channel">
      <span class="slot">{links.slot(path)}{links.mark(path)}</span>
      <strong>{links.name(path)}</strong>
    </button>

    <div class="leds">
      <span class="led" class:on={clip} style:--c="var(--danger)">CLIP</span>
      {#if output}
        <span class="led" class:on={comp} style:--c={COMP_COLOR}>CMP</span>
        <span class="led" class:on={limit} style:--c={LIMIT_COLOR}>LIM</span>
      {/if}
    </div>

    <div class="body">
      <BigMeter
        {level}
        {clip}
        {comp}
        {limit}
        compThreshold={output && output.compressor.ratio > 0 ? output.compressor.threshold_db : null}
        limitThreshold={output ? output.limiter.threshold_db : null}
      />
      <Fader
        value={channel.gain_db}
        label={links.name(path)}
        disabled={!app.editable("gain_db")}
        onchange={(db) => app.set(`${path}.gain_db`, db)}
      />
    </div>

    <!-- SIG between the meter and MUTE: is anything coming in / going out? -->
    <span class="led sig" class:on={sig.lit} style:--c={SIGNAL_COLOR} title="Signal">SIG</span>

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
    /* Muted: red diagonal hatching (the name keeps its channel colour, which can itself be
       red). */
    background-image: repeating-linear-gradient(
      -45deg,
      rgb(255 77 94 / 0.3) 0 4px, /* --danger at 30 % */
      transparent 4px 16px
    );
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
    /* No shrinking below the fader's own height: it would overflow under MUTE and hide −. */
    flex: 1;
    display: flex;
    justify-content: center;
    gap: 6px;
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
