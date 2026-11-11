<script lang="ts">
  // Frequency response of one channel (filters + PEQ + GEQ), computed from its settings, with
  // the total curves of other channels picked in the "Compare with" row. The PEQ bands are
  // edited on the graph: drag a band's marker (horizontally: frequency, vertically: gain, for
  // peak and shelf bands), turn the mouse wheel over it for its Q.
  import { app } from "../lib/app.svelte";
  import { links } from "../lib/links.svelte";
  import { overlays } from "../lib/overlays.svelte";
  import { channelResponse, F_MAX, F_MIN, usesGain } from "../lib/response";
  import { formatDb, formatHz, formatQ, logIndexStep, logSnap } from "../lib/scale";
  import { throttleLatest } from "../lib/throttle";
  import type { Channel, InputChannel, OutputChannel, PeqBand } from "../lib/types";
  import ChipBar from "./ChipBar.svelte";

  interface Props {
    path: string;
    /** Params › EQ: one small graph per channel, titled with the channel, without the
     * "Compare with" row and the note. */
    compact?: boolean;
    title?: string;
  }

  let { path, compact = false, title = "Frequency response" }: Props = $props();

  const isOutput = $derived(path.startsWith("outputs."));
  const index = $derived(Number(path.split(".")[1]));
  const channel = $derived(
    isOutput
      ? (app.device?.outputs[index] as OutputChannel | undefined)
      : (app.device?.inputs[index] as InputChannel | undefined),
  );
  const profile = $derived(app.hello?.profile);
  const limits = $derived(app.hello?.limits);
  const editable = $derived(app.editable("peq"));

  // --- editing the PEQ bands on the graph ---------------------------------------------------------
  type BandValues = Pick<PeqBand, "freq_hz" | "gain_db" | "q">;
  /** Values shown for one band while it is edited, until the device has them (or 2 s pass). */
  let preview = $state<{ band: number; values: BandValues } | null>(null);
  let dragging = $state<number | null>(null);
  let hover = $state<number | null>(null);
  /** The dB scale does not move while a band is dragged (the pointer maps to fixed values). */
  let frozenTop = $state<number | null>(null);
  let settle: ReturnType<typeof setTimeout> | undefined;
  let svg = $state<SVGSVGElement>();
  const sender = throttleLatest(
    ({ band, values }: { band: number; values: BandValues }) => app.set(`${path}.peq.${band}`, values),
    100,
  );

  /** The channel as shown: with the band being edited at its local values. */
  const shown = $derived<Channel | undefined>(
    channel && preview
      ? {
          ...channel,
          peq: channel.peq.map((b, n) => (n === preview!.band ? { ...b, ...preview!.values } : b)),
        }
      : channel,
  );
  $effect(() => {
    // Back to the device's values once it has the edited ones.
    if (!preview || dragging !== null || !channel) return;
    const band = channel.peq[preview.band];
    const v = preview.values;
    if (
      band &&
      Math.abs(band.freq_hz / v.freq_hz - 1) < 0.005 &&
      Math.abs(band.gain_db - v.gain_db) < 0.05 &&
      Math.abs(band.q / v.q - 1) < 0.01
    ) {
      preview = null;
    }
  });

  function typeName(band: number): string {
    return profile?.peq_types[shown?.peq[band]?.type ?? 0] ?? "Peak";
  }

  function valuesOf(band: number): BandValues | null {
    const b = shown?.peq[band];
    return b ? { freq_hz: b.freq_hz, gain_db: b.gain_db, q: b.q } : null;
  }

  function edit(band: number, values: BandValues) {
    clearTimeout(settle);
    preview = { band, values };
    sender.push({ band, values });
    if (dragging === null) settle = setTimeout(() => (preview = null), 2000);
  }

  function pointer(event: PointerEvent | WheelEvent): [number, number] {
    const rect = svg!.getBoundingClientRect();
    return [event.clientX - rect.left, event.clientY - rect.top];
  }

  function down(event: PointerEvent, band: number) {
    if (!editable) return;
    event.preventDefault();
    (event.currentTarget as Element).setPointerCapture(event.pointerId);
    if (preview && preview.band !== band) sender.flush();
    clearTimeout(settle);
    frozenTop = topDb;
    dragging = band;
  }

  function move(event: PointerEvent) {
    if (dragging === null || !svg || !profile || !limits) return;
    const current = valuesOf(dragging);
    if (!current) return;
    const [px, py] = pointer(event);
    const values = {
      ...current,
      freq_hz: logSnap(hzAt(px), profile.freq_min_hz, profile.freq_max_hz, profile.freq_steps),
    };
    if (usesGain(typeName(dragging))) {
      const [lo, hi] = limits.eq_gain_db;
      values.gain_db = Math.round(Math.min(hi, Math.max(lo, dbAt(py))) * 10) / 10;
    }
    if (values.freq_hz !== current.freq_hz || values.gain_db !== current.gain_db) {
      edit(dragging, values);
    }
  }

  function up() {
    if (dragging === null) return;
    sender.flush();
    dragging = null;
    frozenTop = null;
    settle = setTimeout(() => (preview = null), 2000);
  }

  // Mouse wheel over a marker: its Q, one device step per notch (up: narrower). Not passive, so
  // that it does not scroll the page; elsewhere on the graph the wheel scrolls as usual.
  const WHEEL_NOTCH = 50; // px of scroll per step (a mouse notch is ~100 px, trackpads send less)
  let wheelBand: number | null = null;
  let wheelAcc = 0;
  $effect(() => {
    const el = svg;
    if (!el) return;
    const onWheel = (event: WheelEvent) => {
      if (!editable || !profile || dragging !== null) return;
      const [px, py] = pointer(event);
      const hit = markers.find((m) => Math.hypot(m.cx - px, m.cy - py) <= 16);
      if (!hit) return;
      event.preventDefault();
      const band = hit.n - 1;
      if (wheelBand !== band) wheelAcc = 0;
      wheelBand = band;
      const unit = event.deltaMode === 1 ? 33 : event.deltaMode === 2 ? 400 : 1;
      wheelAcc += event.deltaY * unit;
      const steps = Math.trunc(wheelAcc / WHEEL_NOTCH);
      if (steps === 0) return;
      wheelAcc -= steps * WHEEL_NOTCH;
      const current = valuesOf(band);
      if (!current) return;
      let q = current.q;
      for (let i = 0; i < Math.abs(steps); i++) {
        q = logIndexStep(q, profile.q_min, profile.q_max, profile.q_steps, steps < 0 ? 1 : -1);
      }
      if (q !== current.q) edit(band, { ...current, q });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  });

  const active = $derived(dragging ?? hover);
  const readout = $derived.by(() => {
    if (active === null) return "";
    const v = valuesOf(active);
    if (!v) return "";
    const gain = usesGain(typeName(active)) ? ` · ${formatDb(v.gain_db)} dB` : "";
    return `Band ${active + 1} · ${formatHz(v.freq_hz)} Hz${gain} · Q ${formatQ(v.q)}`;
  });

  const response = $derived(
    shown && profile ? channelResponse(shown, profile.peq_types, profile.slopes) : null,
  );

  // Other channels to overlay (their total curve only); one per link group when merging (the
  // members share their filters and EQ).
  const allChannels = $derived<[string, Channel][]>(
    [
      ...(app.device?.inputs ?? []).map((c, i) => [`inputs.${i}`, c] as [string, Channel]),
      ...(app.device?.outputs ?? []).map((c, i) => [`outputs.${i}`, c] as [string, Channel]),
    ].filter(([p]) => links.isShown(p)),
  );
  const others = $derived(
    profile
      ? allChannels
          .filter(([p]) => !compact && p !== path && overlays.paths.includes(p))
          .map(([p, c]) => ({
            path: p,
            name: `${links.slot(p)} ${links.name(p)}`.trim(),
            color: app.color(p),
            total: channelResponse(c, profile.peq_types, profile.slopes).total,
          }))
      : [],
  );

  let width = $state(600);
  const HEIGHT = 240;
  const PAD = { left: 34, right: 16, top: 8, bottom: 20 };
  const BOTTOM_DB = -30;
  const topDb = $derived(
    frozenTop ??
    (response
      ? Math.max(
          12,
          Math.ceil((Math.max(...response.total, ...others.flatMap((o) => o.total)) + 2) / 6) * 6,
        )
      : 12),
  );

  const GRID_HZ = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000];
  const MINOR_HZ = [30, 40, 60, 70, 80, 90, 300, 400, 600, 700, 800, 900, 3000, 4000, 6000, 7000, 8000, 9000];
  const label = (hz: number) => (hz >= 1000 ? `${hz / 1000}k` : `${hz}`);

  const x = (hz: number) =>
    PAD.left + ((width - PAD.left - PAD.right) * Math.log(hz / F_MIN)) / Math.log(F_MAX / F_MIN);
  const y = (dbValue: number) => {
    const clamped = Math.min(topDb, Math.max(BOTTOM_DB - 6, dbValue));
    return PAD.top + ((HEIGHT - PAD.top - PAD.bottom) * (topDb - clamped)) / (topDb - BOTTOM_DB);
  };
  /** Inverse of `x` and `y`: the frequency and the gain at a point of the plot. */
  const hzAt = (px: number) =>
    F_MIN * (F_MAX / F_MIN) ** ((px - PAD.left) / (width - PAD.left - PAD.right));
  const dbAt = (py: number) =>
    topDb - ((py - PAD.top) * (topDb - BOTTOM_DB)) / (HEIGHT - PAD.top - PAD.bottom);
  const dbLines = $derived(
    Array.from({ length: Math.floor((topDb - BOTTOM_DB) / 6) + 1 }, (_, i) => topDb - 6 * i),
  );

  function line(curve: number[]): string {
    if (!response) return "";
    return curve
      .map((v, i) => `${i ? "L" : "M"}${x(response.freqs[i]!).toFixed(1)},${y(v).toFixed(1)}`)
      .join("");
  }

  /** Band markers, numbered like the list, at the band's frequency and gain (0 dB for the types
   * without a gain). Every band has one, so that it can be grabbed; it is greyed when the band
   * does nothing: off, a peak or shelf at 0 dB, or the whole EQ bypassed. */
  const markers = $derived(
    shown
      ? shown.peq.map((b, band) => {
          const gain = usesGain(typeName(band));
          return {
            n: band + 1,
            cx: x(b.freq_hz),
            cy: y(gain ? b.gain_db : 0),
            off: shown.peq_bypass || b.bypass || (gain && b.gain_db === 0),
          };
        })
      : [],
  );
</script>

<section class="card graph" class:compact>
  <header>
    <h2>{title}</h2>
    <span class="legend">
      <span class="key total"></span>total
      <span class="key xo"></span>HPF / LPF
      <span class="key band"></span>EQ bands
      {#if response?.geq}<span class="key geq"></span>GEQ{/if}
      {#each others as o (o.path)}<span class="key" style:background={o.color}></span><span style:color={o.color}>{o.name}</span>{/each}
    </span>
  </header>
  {#if !compact}
  <div class="compare">
    <span class="muted">Compare with</span>
    <ChipBar
      items={allChannels
        .filter(([p]) => p !== path)
        .map(([p]) => ({ key: p, label: links.slot(p), color: app.color(p) }))}
      selected={overlays.paths.filter((p) => p !== path)}
      onselect={(p) => overlays.toggle(p)}
      label="Channels to overlay"
    />
  </div>
  {/if}
  <div class="plot" bind:clientWidth={width}>
    {#if response}
      <svg
        bind:this={svg}
        {width}
        height={HEIGHT}
        role="img"
        aria-label="Frequency response of the channel"
      >
        <defs>
          <clipPath id={`clip-${path}`}>
            <rect x={PAD.left} y={PAD.top} width={width - PAD.left - PAD.right}
              height={HEIGHT - PAD.top - PAD.bottom} />
          </clipPath>
        </defs>
        {#each MINOR_HZ as hz (hz)}
          <line class="minor" x1={x(hz)} x2={x(hz)} y1={PAD.top} y2={HEIGHT - PAD.bottom} />
        {/each}
        {#each GRID_HZ as hz (hz)}
          <line class="grid" x1={x(hz)} x2={x(hz)} y1={PAD.top} y2={HEIGHT - PAD.bottom} />
          <text class="hz" x={x(hz)} y={HEIGHT - 5}>{label(hz)}</text>
        {/each}
        {#each dbLines as d (d)}
          <line class="grid" class:zero={d === 0} x1={PAD.left} x2={width - PAD.right} y1={y(d)} y2={y(d)} />
          <text class="db" x={PAD.left - 4} y={y(d) + 3}>{d > 0 ? `+${d}` : d}</text>
        {/each}
        <g clip-path={`url(#clip-${path})`}>
          {#each response.peq as p (p.band)}
            <path class="band" d={line(p.curve)} />
          {/each}
          {#if response.geq}<path class="geq" d={line(response.geq)} />{/if}
          {#each others as o (o.path)}
            <path class="other" style:stroke={o.color} d={line(o.total)} />
          {/each}
          <path class="xo" d={line(response.crossover)} />
          <path class="total" d={line(response.total)} />
          {#each markers as m (m.n)}
            <g
              class="marker"
              class:editable
              class:active={active === m.n - 1}
              class:off={m.off}
              role="slider"
              tabindex="-1"
              aria-label={`EQ band ${m.n}: drag for frequency and gain, mouse wheel for Q`}
              aria-valuenow={shown?.peq[m.n - 1]?.freq_hz}
              onpointerdown={(e) => down(e, m.n - 1)}
              onpointermove={move}
              onpointerup={up}
              onpointercancel={up}
              onpointerenter={() => (hover = m.n - 1)}
              onpointerleave={() => {
                if (hover === m.n - 1) hover = null;
              }}
            >
              <circle class="hit" cx={m.cx} cy={m.cy} r="16" />
              <circle cx={m.cx} cy={m.cy} r="8" />
              <text class="n" x={m.cx} y={m.cy + 3.5}>{m.n}</text>
            </g>
          {/each}
        </g>
        {#if readout}
          <text class="readout" x={PAD.left + 8} y={PAD.top + 14}>{readout}</text>
        {/if}
      </svg>
    {/if}
  </div>
  {#if !compact}
  <p class="note muted">
    Computed from the settings with textbook filter shapes; the DSP's exact curves may differ
    slightly. Channel gain, dynamics and delay are not included. Drag a band's marker to set its
    frequency and gain; turn the mouse wheel over it for its Q.
  </p>
  {/if}
</section>

<style>
  .graph {
    margin-bottom: 10px;
    padding: 10px 12px;
  }
  .graph.compact {
    margin: 0;
  }
  header {
    display: flex;
    flex-wrap: wrap;
    align-items: baseline;
    justify-content: space-between;
    gap: 4px 12px;
  }
  h2 {
    margin: 0 0 6px;
    font-size: 1rem;
  }
  .legend {
    display: flex;
    align-items: center;
    gap: 4px 6px;
    flex-wrap: wrap;
    font-size: 0.75rem;
    color: var(--muted);
  }
  .key {
    display: inline-block;
    width: 14px;
    height: 3px;
    border-radius: 2px;
    margin-left: 6px;
  }
  .key.total {
    background: var(--accent);
  }
  .key.xo {
    background: var(--info);
  }
  .key.band {
    background: var(--warn);
  }
  .key.geq {
    background: #c77dff;
  }
  .plot {
    width: 100%;
    overflow: hidden;
  }
  svg {
    display: block;
    background: #0b0c0f;
    border-radius: 6px;
  }
  line.grid {
    stroke: rgba(255, 255, 255, 0.12);
  }
  line.minor {
    stroke: rgba(255, 255, 255, 0.05);
  }
  line.zero {
    stroke: rgba(255, 255, 255, 0.35);
  }
  text {
    fill: var(--muted);
    font-size: 10px;
    font-variant-numeric: tabular-nums;
  }
  text.hz {
    text-anchor: middle;
  }
  text.db {
    text-anchor: end;
  }
  path {
    fill: none;
    stroke-linejoin: round;
  }
  path.total {
    stroke: var(--accent);
    stroke-width: 2.5;
  }
  path.xo {
    stroke: var(--info);
    stroke-width: 1.5;
    stroke-dasharray: 5 4;
    opacity: 0.8;
  }
  path.band {
    stroke: var(--warn);
    stroke-width: 1;
    opacity: 0.55;
  }
  path.other {
    stroke-width: 1.8;
    opacity: 0.85;
  }
  .compare {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    align-items: center;
    gap: 8px;
    font-size: 0.8rem;
  }
  .compare :global(.chips) {
    padding-bottom: 6px;
  }
  .compare :global(.chips button) {
    min-height: 30px;
    padding: 0 10px;
    font-size: 0.8rem;
  }
  path.geq {
    stroke: #c77dff;
    stroke-width: 1.2;
    opacity: 0.7;
  }
  circle {
    fill: var(--panel-2);
    stroke: var(--warn);
    stroke-width: 1.5;
  }
  circle.hit {
    fill: transparent;
    stroke: none;
  }
  /* A band that does nothing (off, at 0 dB, EQ bypassed): greyed. */
  .marker.off circle:not(.hit) {
    stroke: var(--muted);
    fill: #16181d;
  }
  .marker.off text.n {
    fill: var(--muted);
  }
  .marker.editable {
    cursor: grab;
    touch-action: none; /* a drag on a marker edits the band instead of scrolling */
  }
  .marker.active circle:not(.hit) {
    stroke: var(--accent);
    stroke-width: 2.5;
  }
  .marker.editable.active {
    cursor: grabbing;
  }
  text.readout {
    fill: var(--text);
    font-size: 11px;
    font-weight: 600;
    pointer-events: none;
  }
  text.n {
    fill: var(--text);
    font-size: 10px;
    font-weight: 700;
    text-anchor: middle;
  }
  .note {
    margin: 6px 0 0;
    font-size: 0.75rem;
  }
</style>
