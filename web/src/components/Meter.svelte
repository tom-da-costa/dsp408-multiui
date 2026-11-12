<script lang="ts">
  import {
    meterRange,
    segmentGaps,
    segmentLevel,
    segmentZoneStart,
  } from "../lib/meterrange.svelte";
  import { METER_BACKGROUND_OPACITY, meterFill, meterGradient, meterPos } from "../lib/scale";
  import { signalLit } from "../lib/signal.svelte";

  // Colour zones, dimmed behind the level; the fill reveals them up to the level, turns to
  // the limiter's or the compressor's colour while it acts, and all red on clip. Linear in dBu
  // over the range set in Settings (−40 to +20 dBu by default).

  interface Props {
    level: number | null; // dB; null = no data
    clip?: boolean;
    limit?: boolean | null;
    comp?: boolean | null;
    floor?: number;
  }

  let { level, clip = false, limit = null, comp = null, floor = -90 }: Props = $props();

  const PEAK_HOLD_MS = 1500;
  const CLIP_LATCH_MS = 2000;

  let peak = $state<number | null>(null);
  let peakAt = 0;
  let clipUntil = $state(0);
  let now = $state(performance.now());

  const bottom = $derived(Math.max(meterRange.min, floor));
  const dbToPos = $derived((db: number) => meterPos(db, bottom, meterRange.max));
  // Segmented (Settings): the level reaches the top of its segment, a zone starts on a segment.
  const step = $derived(meterRange.segment);
  const ZONES = $derived(
    meterGradient("to top", (db) => dbToPos(segmentZoneStart(db, bottom, step))),
  );
  const gaps = $derived(segmentGaps("to top", bottom, meterRange.max, step));
  const pos = $derived(level === null ? 0 : dbToPos(segmentLevel(level, bottom, step)));
  const peakPos = $derived(peak === null ? 0 : dbToPos(segmentLevel(peak, bottom, step)));
  const clipLit = $derived(clip || clipUntil > now);
  const sig = signalLit(() => level);

  $effect(() => {
    const t = performance.now();
    now = t;
    if (level !== null && (peak === null || level >= peak || t - peakAt > PEAK_HOLD_MS)) {
      peak = level;
      peakAt = t;
    }
    if (clip) clipUntil = t + CLIP_LATCH_MS;
  });
</script>

<div class="meter" class:nodata={level === null} aria-label="level meter">
  <div class="leds">
    <span class="led sig" class:on={sig.lit} title="Signal">SIG</span>
    <span class="led clip" class:on={clipLit} title="Clip">CLIP</span>
    {#if limit !== null}<span class="led lim" class:on={limit} title="Limiter">LIM</span>{/if}
    {#if comp !== null}<span class="led comp" class:on={comp} title="Compressor">CMP</span>{/if}
  </div>
  <div class="bar">
    <div class="zones" style:background={ZONES} style:opacity={METER_BACKGROUND_OPACITY}></div>
    <div
      class="fill"
      class:clipping={clip}
      class:stepped={step > 0}
      style:background={clip ? undefined : meterFill(ZONES, limit, comp)}
      style:clip-path={`inset(${((1 - pos) * 100).toFixed(2)}% 0 0 0)`}
    ></div>
    {#if gaps}<div class="gaps" style:background={gaps}></div>{/if}
    {#if peakPos > 0}<div class="peak" style:bottom={`${peakPos * 100}%`}></div>{/if}
    <!-- 0 dBu (compressor / limiter / gate thresholds are on the same scale) -->
    {#if bottom < 0 && meterRange.max > 0}
      <div class="tick" style:bottom={`${dbToPos(0) * 100}%`} title="0 dBu"></div>
    {/if}
  </div>
</div>

<style>
  .meter {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 4px;
    height: 100%;
  }
  .leds {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .led {
    font-size: 0.6rem;
    font-weight: 700;
    letter-spacing: 0.02em;
    padding: 1px 3px;
    border-radius: 3px;
    background: var(--panel-2);
    color: var(--muted);
    text-align: center;
  }
  .sig.on {
    background: var(--accent);
    color: var(--accent-text);
  }
  .clip.on {
    background: var(--danger);
    color: #fff;
  }
  .lim.on {
    background: var(--warn);
    color: #000;
  }
  .comp.on {
    background: var(--info);
    color: #000;
  }
  .bar {
    position: relative;
    flex: 1;
    width: 10px;
    min-height: 80px;
    border-radius: 3px;
    background: #0b0c0f;
    overflow: hidden;
  }
  .zones,
  .fill,
  .gaps {
    position: absolute;
    inset: 0;
  }
  .fill {
    transition: clip-path 120ms linear;
  }
  /* Segmented: a segment lights or goes out at once, like an LED. */
  .fill.stepped {
    transition: none;
  }
  .fill.clipping {
    background: var(--danger);
  }
  .peak {
    position: absolute;
    left: 0;
    right: 0;
    height: 2px;
    background: #fff;
  }
  .tick {
    position: absolute;
    left: 0;
    right: 0;
    height: 1px;
    background: rgba(255, 255, 255, 0.35);
  }
  .nodata .bar {
    opacity: 0.4;
  }
</style>
