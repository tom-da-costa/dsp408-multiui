<script lang="ts">
  // Horizontal live level of one channel, with its CLIP / LIM / COMP indicators.
  import { app } from "../lib/app.svelte";
  import { formatDb, meterPos } from "../lib/scale";

  interface Props {
    path: string; // "inputs.0" / "outputs.3"
    compact?: boolean;
  }

  let { path, compact = false }: Props = $props();

  const isOutput = $derived(path.startsWith("outputs."));
  const index = $derived(Number(path.split(".")[1]));
  const inputCount = $derived(app.hello?.profile.input_count ?? 4);
  const meterIndex = $derived(isOutput ? inputCount + index : index);
  const level = $derived(app.meters?.levels?.[meterIndex] ?? null);
  const clip = $derived(app.meters?.clip?.[meterIndex] ?? false);
  const limit = $derived(isOutput ? (app.meters?.limit?.[index] ?? null) : null);
  const comp = $derived(isOutput ? (app.meters?.comp?.[index] ?? null) : null);
  const floor = $derived(app.hello?.profile.meter_floor_db ?? -90);
</script>

<div class="meter" class:compact aria-label="Level">
  <div class="level" class:clip style:width={`${meterPos(level, floor) * 100}%`}></div>
  <span class="db">{level === null ? "—" : `${formatDb(level)} dB`}</span>
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
