<script lang="ts">
  import { meterDbToPos as dbToPos, meterGradient } from "../lib/scale";

  // Fixed colour zones; the fill reveals them up to the level, and turns all red on clip.
  const ZONES = meterGradient("to top", dbToPos);

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

  const pos = $derived(level === null || level <= floor ? 0 : dbToPos(level));
  const peakPos = $derived(peak === null || peak <= floor ? 0 : dbToPos(peak));
  const clipLit = $derived(clip || clipUntil > now);

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
    <span class="led clip" class:on={clipLit} title="Clip">CLIP</span>
    {#if limit !== null}<span class="led lim" class:on={limit} title="Limiter">LIM</span>{/if}
    {#if comp !== null}<span class="led comp" class:on={comp} title="Compressor">CMP</span>{/if}
  </div>
  <div class="bar">
    <div
      class="fill"
      class:clipping={clip}
      style:background={clip ? undefined : ZONES}
      style:clip-path={`inset(${((1 - pos) * 100).toFixed(2)}% 0 0 0)`}
    ></div>
    {#if peakPos > 0}<div class="peak" style:bottom={`${peakPos * 100}%`}></div>{/if}
    <!-- 0 dBu (compressor / limiter / gate thresholds are on the same scale) -->
    <div class="tick" style:bottom={`${dbToPos(0) * 100}%`} title="0 dBu"></div>
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
  .fill {
    position: absolute;
    inset: 0;
    transition: clip-path 120ms linear;
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
