<script lang="ts">
  // Horizontal live level of one channel, graduated every 10 dB (numbers below: every 10 dB,
  // every 20 dB when compact), with its CLIP / LIM / COMP indicators: small, in the bar; or, with
  // `indicators`, as a row under the meter like the Live view's (SIG first, CLIP held 2 s).
  import { app } from "../lib/app.svelte";
  import { links } from "../lib/links.svelte";
  import {
    meterRange,
    meterTicks,
    segmentGaps,
    segmentLevel,
    segmentZoneStart,
  } from "../lib/meterrange.svelte";
  import { SIGNAL_COLOR, signalLit } from "../lib/signal.svelte";
  import {
    COMP_COLOR,
    formatDb,
    LIMIT_COLOR,
    METER_BACKGROUND_OPACITY,
    meterFill,
    meterGradient,
    meterPos,
  } from "../lib/scale";

  interface Props {
    path: string; // "inputs.0" / "outputs.3"
    compact?: boolean;
    /** CLIP / CMP / LIM as a row under the meter (channel page, All-in-one). */
    indicators?: boolean;
  }

  let { path, compact = false, indicators = false }: Props = $props();

  // Merged over the link group when "Merge linked channels" is on.
  const meter = $derived(links.meter(path));
  const level = $derived(meter.level);
  const clip = $derived(meter.clip);
  const limit = $derived(meter.limit);
  const comp = $derived(meter.comp);

  // CLIP stays lit for 2 s in the indicator row, so that a short overload is seen (as in Live).
  const CLIP_LATCH_MS = 2000;
  let clipUntil = $state(0);
  let now = $state(0);
  $effect(() => {
    now = performance.now();
    if (clip) clipUntil = now + CLIP_LATCH_MS;
  });
  $effect(() => {
    if (clipUntil <= now) return;
    const timer = setTimeout(() => (now = performance.now()), clipUntil - now + 10);
    return () => clearTimeout(timer);
  });
  const clipHeld = $derived(clip || clipUntil > now);
  const sig = signalLit(() => level);

  // The range set in Settings, as the Live meters (below the device's floor: shown as empty).
  const floor = $derived(Math.max(meterRange.min, app.hello?.profile.meter_floor_db ?? -90));
  const top = $derived(meterRange.max);
  // Segmented (Settings): the level reaches the top of its segment, a zone starts on a segment.
  const step = $derived(meterRange.segment);
  const zones = $derived(
    meterGradient("to right", (db) => meterPos(segmentZoneStart(db, floor, step), floor, top)),
  );
  const gaps = $derived(segmentGaps("to right", floor, top, step));
  const pos = $derived(
    meterPos(level === null ? null : segmentLevel(level, floor, step), floor, top),
  );

  // Graduations strictly inside the bar, every 10 dB.
  const ticks = $derived(meterTicks(floor, top).filter((db) => db > floor && db < top));
  const labels = $derived(ticks.filter((db) => !compact || db % 20 === 0));
  const at = (db: number) => `${(meterPos(db, floor, top) * 100).toFixed(2)}%`;
</script>

<div class="bar" class:compact>
<div class="meter" class:compact aria-label="Level">
  <div class="zones" style:background={zones} style:opacity={METER_BACKGROUND_OPACITY}></div>
  <div
    class="level"
    class:clip
    class:stepped={step > 0}
    style:background={clip ? undefined : meterFill(zones, limit, comp)}
    style:clip-path={`inset(0 ${((1 - pos) * 100).toFixed(2)}% 0 0)`}
  ></div>
  {#if gaps}<div class="gaps" style:background={gaps}></div>{/if}
  {#each ticks as db (db)}
    <span class="tick" class:zero={db === 0} style:left={at(db)} aria-hidden="true"></span>
  {/each}
  <span class="db">{level === null ? "—" : `${formatDb(level)} dBu`}</span>
  {#if !indicators}
    {#if clip}<span class="led clip">CLIP</span>{/if}
    {#if limit !== null}<span class="led" class:on={limit}>LIM</span>{/if}
    {#if comp !== null}<span class="led" class:on={comp}>COMP</span>{/if}
  {/if}
</div>
<div class="scale" aria-hidden="true">
  {#each labels as db (db)}
    <span style:left={at(db)}>{db > 0 ? `+${db}` : db}</span>
  {/each}
</div>
{#if indicators}
  <div class="indicators">
    <span class="big" class:lit={sig.lit} style:--c={SIGNAL_COLOR} title="Signal">SIG</span>
    <span class="big" class:lit={clipHeld} style:--c="var(--danger)">CLIP</span>
    {#if comp !== null}<span class="big" class:lit={comp} style:--c={COMP_COLOR}>CMP</span>{/if}
    {#if limit !== null}<span class="big" class:lit={limit} style:--c={LIMIT_COLOR}>LIM</span>{/if}
  </div>
{/if}
</div>

<style>
  .bar {
    display: grid;
    gap: 1px;
  }
  .meter {
    position: relative;
    display: flex;
    align-items: center;
    gap: 6px;
    height: 28px;
    padding: 0 8px;
    border-radius: 6px;
    background: #0b0c0f;
    overflow: hidden;
  }
  .meter.compact {
    height: 22px;
    gap: 4px;
    padding: 0 6px;
  }
  .zones,
  .gaps {
    position: absolute;
    inset: 0;
  }
  .level {
    position: absolute;
    inset: 0;
    opacity: 0.65;
    transition: clip-path 0.12s linear;
  }
  /* Segmented: a segment lights or goes out at once, like an LED. */
  .level.stepped {
    transition: none;
  }
  .level.clip {
    background: var(--danger);
    opacity: 0.9;
  }
  .db {
    position: relative;
    flex: 1;
    font-variant-numeric: tabular-nums;
    font-size: 0.85rem;
  }
  .compact .db {
    font-size: 0.75rem;
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
  .compact .led {
    font-size: 0.6rem;
    padding: 1px 4px;
  }
  .led.on {
    background: var(--warn);
    color: #000;
  }
  .led.clip {
    background: var(--danger);
    color: #fff;
  }
  .tick {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 1px;
    background: rgba(255, 255, 255, 0.12);
  }
  .tick.zero {
    background: rgba(255, 255, 255, 0.45);
  }
  .scale {
    position: relative;
    height: 12px;
  }
  .scale span {
    position: absolute;
    top: 0;
    transform: translateX(-50%);
    font-size: 0.6rem;
    line-height: 12px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }
  .compact .scale {
    height: 11px;
  }
  .indicators {
    /* the whole width, in equal parts */
    display: grid;
    grid-auto-flow: column;
    grid-auto-columns: 1fr;
    gap: 6px;
    margin-top: 4px;
  }
  .big {
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
  .compact .big {
    height: 24px;
    font-size: 0.65rem;
  }
  .big.lit {
    background: var(--c);
    border-color: var(--c);
    color: #000;
    box-shadow: 0 0 10px var(--c);
  }
  .compact .scale span {
    font-size: 0.55rem;
    line-height: 11px;
  }
</style>
