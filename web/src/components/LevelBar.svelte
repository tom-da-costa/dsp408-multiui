<script lang="ts">
  // Horizontal live level of one channel, with its CLIP / LIM / COMP indicators.
  import { app } from "../lib/app.svelte";
  import { links } from "../lib/links.svelte";
  import { formatDb, meterGradient, meterPos } from "../lib/scale";

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
</script>

<div class="meter" class:compact aria-label="Level">
  <div
    class="level"
    class:clip
    style:background={clip ? undefined : zones}
    style:clip-path={`inset(0 ${((1 - pos) * 100).toFixed(2)}% 0 0)`}
  ></div>
  <span class="db">{level === null ? "—" : `${formatDb(level)} dBu`}</span>
  {#if clip}<span class="led clip">CLIP</span>{/if}
  {#if limit !== null}<span class="led" class:on={limit}>LIM</span>{/if}
  {#if comp !== null}<span class="led" class:on={comp}>COMP</span>{/if}
</div>

<style>
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
</style>
