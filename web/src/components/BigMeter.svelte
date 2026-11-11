<script lang="ts">
  // Vertical meter of the Live view: linear dBu scale graduated every 10 dB, colour zones
  // (dimmed behind the level), peak hold, and markers at the compressor and limiter thresholds.
  // The level turns to the limiter's or the compressor's colour while it acts, red on clip.
  import {
    COMP_COLOR,
    LIMIT_COLOR,
    METER_BACKGROUND_OPACITY,
    meterFill,
    meterGradient,
  } from "../lib/scale";

  interface Props {
    level: number | null; // dBu; null = no data
    clip: boolean;
    comp?: boolean;
    limit?: boolean;
    compThreshold?: number | null; // dBu
    limitThreshold?: number | null; // dBu
  }

  let {
    level,
    clip,
    comp = false,
    limit = false,
    compThreshold = null,
    limitThreshold = null,
  }: Props = $props();

  const BOTTOM = -60;
  const TOP = 20; // full scale, +20 dBu
  const TICKS = [20, 10, 0, -10, -20, -30, -40, -50, -60];
  const PEAK_HOLD_MS = 1500;

  const pos = (db: number) => Math.min(1, Math.max(0, (db - BOTTOM) / (TOP - BOTTOM)));
  const ZONES = meterGradient("to top", pos);

  let peak = $state<number | null>(null);
  let peakAt = 0;

  $effect(() => {
    const t = performance.now();
    if (level === null) {
      peak = null; // no live level (server or DSP unreachable): no stale peak either
    } else if ((peak === null || level >= peak || t - peakAt > PEAK_HOLD_MS)) {
      peak = level;
      peakAt = t;
    }
  });

  const fill = $derived(level === null ? 0 : pos(level));
</script>

<div class="meter" class:nodata={level === null}>
  <div class="scale" aria-hidden="true">
    {#each TICKS as db (db)}
      <span style:bottom={`${pos(db) * 100}%`}>{db > 0 ? `+${db}` : db}</span>
    {/each}
  </div>
  <div class="bar" role="meter" aria-label="Level in dBu" aria-valuenow={level ?? BOTTOM}
    aria-valuemin={BOTTOM} aria-valuemax={TOP}>
    <div class="zones" style:background={ZONES} style:opacity={METER_BACKGROUND_OPACITY}></div>
    <div
      class="fill"
      class:clipping={clip}
      style:background={clip ? undefined : meterFill(ZONES, limit, comp)}
      style:clip-path={`inset(${((1 - fill) * 100).toFixed(2)}% 0 0 0)`}
    ></div>
    {#each TICKS as db (db)}
      <div class="tick" class:zero={db === 0} style:bottom={`${pos(db) * 100}%`}></div>
    {/each}
    {#if peak !== null && pos(peak) > 0}
      <div class="peak" style:bottom={`${pos(peak) * 100}%`}></div>
    {/if}
  </div>
  <div class="marks" aria-hidden="true">
    {#if compThreshold !== null}
      <span
        class="mark"
        style:bottom={`${pos(compThreshold) * 100}%`}
        style:--c={COMP_COLOR}
        title={`Compressor threshold ${compThreshold} dBu`}>C</span
      >
    {/if}
    {#if limitThreshold !== null}
      <span
        class="mark"
        style:bottom={`${pos(limitThreshold) * 100}%`}
        style:--c={LIMIT_COLOR}
        title={`Limiter threshold ${limitThreshold} dBu`}>L</span
      >
    {/if}
  </div>
</div>

<style>
  .meter {
    display: grid;
    grid-template-columns: 24px 16px 14px;
    height: 100%;
    min-height: 160px;
  }
  .scale,
  .bar,
  .marks {
    position: relative;
  }
  .scale span {
    position: absolute;
    right: 3px;
    transform: translateY(50%);
    font-size: 0.6rem;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
    line-height: 1;
  }
  .bar {
    border-radius: 3px;
    background: #0b0c0f;
    overflow: hidden;
  }
  .zones,
  .fill {
    position: absolute;
    inset: 0;
  }
  .fill {
    transition: clip-path 120ms linear;
  }
  .fill.clipping {
    background: var(--danger);
  }
  .tick {
    position: absolute;
    left: 0;
    right: 0;
    height: 1px;
    background: rgba(0, 0, 0, 0.55);
  }
  .tick.zero {
    background: rgba(255, 255, 255, 0.5);
  }
  .peak {
    position: absolute;
    left: 0;
    right: 0;
    height: 2px;
    background: #fff;
  }
  .mark {
    position: absolute;
    left: 0;
    transform: translateY(50%);
    font-size: 0.6rem;
    font-weight: 800;
    line-height: 1;
    padding: 1px 2px;
    border-radius: 2px;
    background: var(--c);
    color: #000;
  }
  .mark::before {
    /* a line back across the bar, at the threshold */
    content: "";
    position: absolute;
    right: 100%;
    top: 50%;
    width: 16px;
    height: 2px;
    background: var(--c);
  }
  .nodata .bar {
    opacity: 0.4;
  }
</style>
