<script lang="ts">
  // Horizontal live level of one channel, with its CLIP / LIM / COMP indicators, graduated every
  // 10 dB (numbers below: every 10 dB, every 20 dB when compact).
  import { app } from "../lib/app.svelte";
  import { links } from "../lib/links.svelte";
  import {
    formatDb,
    METER_BACKGROUND_OPACITY,
    meterFill,
    meterGradient,
    meterPos,
  } from "../lib/scale";

  interface Props {
    path: string; // "inputs.0" / "outputs.3"
    compact?: boolean;
  }

  let { path, compact = false }: Props = $props();

  // Merged over the link group when "Merge linked channels" is on.
  const meter = $derived(links.meter(path));
  const level = $derived(meter.level);
  const clip = $derived(meter.clip);
  const limit = $derived(meter.limit);
  const comp = $derived(meter.comp);
  const floor = $derived(app.hello?.profile.meter_floor_db ?? -90);
  const top = 20; // full scale, +20 dBu
  const zones = $derived(meterGradient("to right", (db) => meterPos(db, floor, top)));
  const pos = $derived(meterPos(level, floor, top));

  // Graduations strictly inside the bar, every 10 dB.
  const ticks = $derived(
    Array.from({ length: Math.floor((top - floor) / 10) }, (_, i) => top - 10 * (i + 1)).filter(
      (db) => db > floor,
    ),
  );
  const labels = $derived(ticks.filter((db) => !compact || db % 20 === 0));
  const at = (db: number) => `${(meterPos(db, floor, top) * 100).toFixed(2)}%`;
</script>

<div class="bar" class:compact>
<div class="meter" class:compact aria-label="Level">
  <div class="zones" style:background={zones} style:opacity={METER_BACKGROUND_OPACITY}></div>
  <div
    class="level"
    class:clip
    style:background={clip ? undefined : meterFill(zones, limit, comp)}
    style:clip-path={`inset(0 ${((1 - pos) * 100).toFixed(2)}% 0 0)`}
  ></div>
  {#each ticks as db (db)}
    <span class="tick" class:zero={db === 0} style:left={at(db)} aria-hidden="true"></span>
  {/each}
  <span class="db">{level === null ? "—" : `${formatDb(level)} dBu`}</span>
  {#if clip}<span class="led clip">CLIP</span>{/if}
  {#if limit !== null}<span class="led" class:on={limit}>LIM</span>{/if}
  {#if comp !== null}<span class="led" class:on={comp}>COMP</span>{/if}
</div>
<div class="scale" aria-hidden="true">
  {#each labels as db (db)}
    <span style:left={at(db)}>{db > 0 ? `+${db}` : db}</span>
  {/each}
</div>
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
  .zones {
    position: absolute;
    inset: 0;
  }
  .level {
    position: absolute;
    inset: 0;
    opacity: 0.65;
    transition: clip-path 0.12s linear;
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
  .compact .scale span {
    font-size: 0.55rem;
    line-height: 11px;
  }
</style>
