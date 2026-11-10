<script lang="ts">
  // Frequency response of one channel (filters + PEQ + GEQ), computed from its settings.
  import { app } from "../lib/app.svelte";
  import { channelResponse, F_MAX, F_MIN } from "../lib/response";
  import type { InputChannel, OutputChannel } from "../lib/types";

  interface Props {
    path: string;
  }

  let { path }: Props = $props();

  const isOutput = $derived(path.startsWith("outputs."));
  const index = $derived(Number(path.split(".")[1]));
  const channel = $derived(
    isOutput
      ? (app.device?.outputs[index] as OutputChannel | undefined)
      : (app.device?.inputs[index] as InputChannel | undefined),
  );
  const profile = $derived(app.hello?.profile);
  const response = $derived(
    channel && profile ? channelResponse(channel, profile.peq_types, profile.slopes) : null,
  );

  let width = $state(600);
  const HEIGHT = 240;
  const PAD = { left: 34, right: 16, top: 8, bottom: 20 };
  const BOTTOM_DB = -30;
  const topDb = $derived(
    response ? Math.max(12, Math.ceil((Math.max(...response.total) + 2) / 6) * 6) : 12,
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
  const dbLines = $derived(
    Array.from({ length: Math.floor((topDb - BOTTOM_DB) / 6) + 1 }, (_, i) => topDb - 6 * i),
  );

  function line(curve: number[]): string {
    if (!response) return "";
    return curve
      .map((v, i) => `${i ? "L" : "M"}${x(response.freqs[i]!).toFixed(1)},${y(v).toFixed(1)}`)
      .join("");
  }

  /** Band markers: at the band's frequency and gain (peak / shelf), numbered like the list. */
  const markers = $derived(
    channel && response
      ? response.peq.map(({ band }) => {
          const b = channel.peq[band]!;
          return { n: band + 1, cx: x(b.freq_hz), cy: y(b.gain_db) };
        })
      : [],
  );
</script>

<section class="card graph">
  <header>
    <h2>Frequency response</h2>
    <span class="legend">
      <span class="key total"></span>total
      <span class="key xo"></span>HPF / LPF
      <span class="key band"></span>EQ bands
      {#if response?.geq}<span class="key geq"></span>GEQ{/if}
    </span>
  </header>
  <div class="plot" bind:clientWidth={width}>
    {#if response}
      <svg {width} height={HEIGHT} role="img" aria-label="Frequency response of the channel">
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
          <path class="xo" d={line(response.crossover)} />
          <path class="total" d={line(response.total)} />
          {#each markers as m (m.n)}
            <circle cx={m.cx} cy={m.cy} r="8" />
            <text class="n" x={m.cx} y={m.cy + 3.5}>{m.n}</text>
          {/each}
        </g>
      </svg>
    {/if}
  </div>
  <p class="note muted">
    Computed from the settings with textbook filter shapes; the DSP's exact curves may differ
    slightly. Channel gain, dynamics and delay are not included.
  </p>
</section>

<style>
  .graph {
    margin-bottom: 10px;
    padding: 10px 12px;
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
