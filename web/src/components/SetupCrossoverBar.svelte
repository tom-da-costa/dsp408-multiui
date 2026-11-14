<script lang="ts">
  // Setup wizard, Crossover step: the whole system on one flat bar, 20 Hz – 20 kHz on a log
  // scale. Each main way is a band in its colour (its speakers' range drawn faintly behind),
  // with a handle at the subsonic high-pass and at every crossover: drag it (or use the arrow
  // keys) to move that frequency. The fields under the bar show the same values.
  import {
    boundaries,
    mainWays,
    orderedWays,
    wayFilters,
    wiring,
    type FilterSetting,
    type Topology,
  } from "../lib/setup";
  import { wizard } from "../lib/wizard.svelte";

  let { topo }: { topo: Topology } = $props();

  const COLORS = ["#3ddc97", "#4da3ff", "#ffb020", "#c38bff", "#ff7a59", "#5ad1e6", "#e6d75a", "#ff5fa2"];
  const MIN_HZ = 20;
  const MAX_HZ = 20000;
  const TICKS = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000];
  const STEP = 2 ** (1 / 24); // arrow keys: 1/24 octave

  const draft = $derived(wizard.draft);
  const ways = $derived(wiring(draft, topo).ways);
  const main = $derived(mainWays(ways));
  const colors = $derived(new Map(orderedWays(ways).map((w, i) => [w.key, COLORS[i % COLORS.length]!])));
  const filters = $derived(wayFilters(draft, ways, topo.slopes));

  interface Handle {
    key: string;
    label: string;
    setting: FilterSetting;
    hz: number;
  }

  // Handles from low to high: the subsonic, then each crossover (only the enabled ones).
  const handles = $derived.by(() => {
    const list: Handle[] = [];
    const lowest = main[0];
    const sub = lowest ? filters.get(lowest.key)?.hpf : null;
    if (lowest && sub) list.push({ key: "subsonic", label: `${lowest.key} subsonic`, setting: draft.subsonic, hz: sub.freq_hz });
    for (const b of boundaries(ways)) {
      const setting = draft.crossovers[b.key];
      const f = filters.get(b.lower.key)?.lpf;
      if (setting && f) list.push({ key: b.key, label: `${b.lower.key} ↔ ${b.upper.key}`, setting, hz: f.freq_hz });
    }
    return list;
  });

  const pos = (hz: number) =>
    (Math.log(Math.min(MAX_HZ, Math.max(MIN_HZ, hz)) / MIN_HZ) / Math.log(MAX_HZ / MIN_HZ)) * 100;
  const hzAt = (fraction: number) => MIN_HZ * (MAX_HZ / MIN_HZ) ** Math.min(1, Math.max(0, fraction));
  /** A readable value: 3 significant digits. */
  const tidy = (hz: number) => {
    const digits = 10 ** Math.max(0, Math.floor(Math.log10(hz)) - 2);
    return Math.round(hz / digits) * digits;
  };
  const label = (hz: number) => (hz >= 1000 ? `${Number((hz / 1000).toFixed(2))}k` : `${Math.round(hz)}`);

  function set(i: number, hz: number) {
    const handle = handles[i];
    if (!handle) return;
    // Between its neighbours, so that the handles keep their order.
    const low = (handles[i - 1]?.hz ?? MIN_HZ) * 1.06;
    const high = (handles[i + 1]?.hz ?? MAX_HZ) / 1.06;
    handle.setting.freqHz = String(tidy(Math.min(high, Math.max(low, hz))));
  }

  let bar = $state<HTMLDivElement>();
  let dragging = $state<number | null>(null);

  function start(e: PointerEvent, i: number) {
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    dragging = i;
  }

  function move(e: PointerEvent) {
    if (dragging === null || !bar) return;
    const box = bar.getBoundingClientRect();
    set(dragging, hzAt((e.clientX - box.left) / box.width));
  }

  function key(e: KeyboardEvent, i: number) {
    const hz = handles[i]?.hz;
    if (hz === undefined) return;
    const factor = e.key === "ArrowRight" || e.key === "ArrowUp" ? STEP : e.key === "ArrowLeft" || e.key === "ArrowDown" ? 1 / STEP : 0;
    if (!factor) return;
    e.preventDefault();
    set(i, hz * (e.shiftKey ? factor ** 6 : factor));
  }
</script>

{#if main.length}
  <section class="card">
    <h2>The system, 20 Hz – 20 kHz</h2>
    <div class="bar" bind:this={bar}>
      {#each main as way (way.key)}
        {@const f = filters.get(way.key)}
        {@const from = f?.hpf?.freq_hz ?? MIN_HZ}
        {@const to = f?.lpf?.freq_hz ?? MAX_HZ}
        {#if Number.isFinite(way.lowHz) && Number.isFinite(way.highHz)}
          <div
            class="range"
            style:left={`${pos(way.lowHz)}%`}
            style:width={`${pos(way.highHz) - pos(way.lowHz)}%`}
            style:--c={colors.get(way.key)}
            title={`${way.key}: speakers ${Math.round(way.lowHz)}–${Math.round(way.highHz)} Hz`}
          ></div>
        {/if}
        <div
          class="band"
          style:left={`${pos(from)}%`}
          style:width={`${pos(to) - pos(from)}%`}
          style:--c={colors.get(way.key)}
        >
          <span>{way.key}</span>
        </div>
      {/each}
      {#each handles as handle, i (handle.key)}
        <div
          class="handle"
          class:active={dragging === i}
          style:left={`${pos(handle.hz)}%`}
          role="slider"
          tabindex="0"
          aria-label={handle.label}
          aria-valuemin={MIN_HZ}
          aria-valuemax={MAX_HZ}
          aria-valuenow={Math.round(handle.hz)}
          aria-valuetext={`${Math.round(handle.hz)} Hz`}
          onpointerdown={(e) => start(e, i)}
          onpointermove={move}
          onpointerup={() => (dragging = null)}
          onpointercancel={() => (dragging = null)}
          onkeydown={(e) => key(e, i)}
        >
          <span class="value">{label(handle.hz)}</span>
        </div>
      {/each}
    </div>
    <div class="ticks" aria-hidden="true">
      {#each TICKS as t (t)}<span style:left={`${pos(t)}%`}>{label(t)}</span>{/each}
    </div>
    <p class="muted hint">
      Drag a handle to move a crossover or the subsonic filter (arrow keys: 1/24 octave, with
      Shift: 1/4). The faint bar under each band is its speakers' range.
    </p>
  </section>
{/if}

<style>
  .bar {
    position: relative;
    height: 64px;
    margin: 26px 12px 4px;
    border-radius: 6px;
    background: #0d0f13;
    box-shadow: inset 0 0 0 1px var(--line);
    touch-action: none;
  }
  .range {
    position: absolute;
    bottom: 6px;
    height: 6px;
    border-radius: 3px;
    background: color-mix(in srgb, var(--c) 40%, transparent);
  }
  .band {
    position: absolute;
    top: 8px;
    height: 34px;
    border-radius: 5px;
    background: color-mix(in srgb, var(--c) 30%, transparent);
    box-shadow: inset 0 0 0 1.5px var(--c);
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .band span {
    font-size: 0.8rem;
    font-weight: 700;
    white-space: nowrap;
  }
  .handle {
    position: absolute;
    top: -6px;
    bottom: -6px;
    width: 28px;
    margin-left: -14px;
    cursor: ew-resize;
    touch-action: none;
    outline: none;
  }
  .handle::before {
    content: "";
    position: absolute;
    left: 12px;
    top: 0;
    bottom: 0;
    width: 4px;
    border-radius: 2px;
    background: #fff;
  }
  .handle:focus-visible::before,
  .handle.active::before {
    background: var(--accent);
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 40%, transparent);
  }
  .value {
    position: absolute;
    bottom: 100%;
    left: 50%;
    transform: translateX(-50%);
    margin-bottom: 2px;
    padding: 0 4px;
    border-radius: 4px;
    background: var(--panel-2);
    font-size: 0.72rem;
    font-weight: 700;
    white-space: nowrap;
  }
  .ticks {
    position: relative;
    height: 16px;
    margin: 0 12px;
  }
  .ticks span {
    position: absolute;
    transform: translateX(-50%);
    font-size: 0.68rem;
    color: var(--muted);
  }
  .hint {
    font-size: 0.8rem;
    margin: 8px 0 0;
  }
</style>
