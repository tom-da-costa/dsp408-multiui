<script lang="ts">
  // Setup wizard: the system as it stands, inputs on the left, outputs on the right, one line
  // per route of the matrix, in the colour of its way. Redrawn at every change.
  import { buildPlan, orderedWays, wayOutputs, type Topology } from "../lib/setup";
  import { wizard } from "../lib/wizard.svelte";

  let { topo }: { topo: Topology } = $props();

  const COLORS = ["#3ddc97", "#4da3ff", "#ffb020", "#c38bff", "#ff7a59", "#5ad1e6", "#e6d75a", "#ff5fa2"];
  const ROW = 26;
  const TOP = 18;
  const IN_W = 112;
  const OUT_X = 200;
  const OUT_W = 156;

  const draft = $derived(wizard.draft);
  const plan = $derived(buildPlan(draft, topo));
  const rows = $derived(Math.max(topo.inputs, topo.outputs));
  const height = $derived(TOP + rows * ROW + 4);
  // The way, its colour and its speaker, per output.
  const byOutput = $derived.by(() => {
    const map = new Map<number, { color: string; speaker: string }>();
    const outs = wayOutputs(draft, topo.outputs);
    orderedWays(draft).forEach((way, n) => {
      for (const o of outs.get(way.id) ?? []) {
        const cabinets = way.cabinets > 1 ? `${way.cabinets}× ` : "";
        map.set(o, {
          color: COLORS[n % COLORS.length]!,
          speaker: `${cabinets}${way.speaker.label || "?"}`,
        });
      }
    });
    return map;
  });
  const inputUsed = (i: number) => plan.outputs.some((o) => o.used && o.sources[i]);
  const y = (row: number) => TOP + row * ROW + ROW / 2;
  const short = (text: string, n: number) => (text.length > n ? `${text.slice(0, n - 1)}…` : text);
</script>

<figure class="card diagram" aria-label="Diagram of the system">
  <svg viewBox={`0 0 360 ${height}`} role="img" aria-label="Inputs routed to outputs">
    <text x="4" y="11" class="head">Inputs</text>
    <text x={OUT_X} y="11" class="head">Outputs → speakers</text>
    {#each plan.outputs as out, o (o)}
      {#each out.sources as on, i (i)}
        {#if on && out.used}
          <path
            d={`M ${IN_W} ${y(i)} C ${(IN_W + OUT_X) / 2} ${y(i)}, ${(IN_W + OUT_X) / 2} ${y(o)}, ${OUT_X} ${y(o)}`}
            stroke={byOutput.get(o)?.color ?? "#888"}
          />
        {/if}
      {/each}
    {/each}
    {#each plan.inputs as input, i (i)}
      <g class:dim={!inputUsed(i)}>
        <rect x="2" y={TOP + i * ROW + 2} width={IN_W - 2} height={ROW - 4} rx="5" />
        <text x="8" y={y(i) + 4} class="slot">{String.fromCharCode(65 + i)}</text>
        <text x="22" y={y(i) + 4}>{input.name}</text>
        {#if input.low_shelf}<text x={IN_W - 6} y={y(i) + 4} class="small end">LS</text>{/if}
      </g>
    {/each}
    {#each plan.outputs as out, o (o)}
      {@const info = byOutput.get(o)}
      <g class:dim={!out.used}>
        <rect
          x={OUT_X}
          y={TOP + o * ROW + 2}
          width={OUT_W}
          height={ROW - 4}
          rx="5"
          style:stroke={info?.color}
        />
        <text x={OUT_X + 6} y={y(o) + 4} class="slot">{o + 1}</text>
        <text x={OUT_X + 20} y={y(o) + 4}>{out.name}</text>
        {#if out.used && info}
          <text x={OUT_X + OUT_W - 6} y={y(o) + 4} class="small end">{short(info.speaker, 13)}</text>
        {/if}
      </g>
    {/each}
  </svg>
  {#if draft.sources.length === 0}<figcaption class="muted">Add a source to start.</figcaption>{/if}
</figure>

<style>
  .diagram {
    margin: 0;
    padding: 8px;
  }
  svg {
    display: block;
    width: 100%;
    max-width: 560px;
    height: auto;
    margin: 0 auto;
  }
  path {
    fill: none;
    stroke-width: 2;
    opacity: 0.85;
  }
  rect {
    fill: var(--panel-2);
    stroke: var(--line);
    stroke-width: 1.5;
  }
  text {
    fill: var(--text);
    font-size: 11px;
  }
  .head {
    fill: var(--muted);
    font-size: 10px;
  }
  .slot {
    fill: var(--muted);
    font-weight: 700;
  }
  .small {
    fill: var(--muted);
    font-size: 9px;
  }
  .end {
    text-anchor: end;
  }
  .dim {
    opacity: 0.4;
  }
  figcaption {
    text-align: center;
    font-size: 0.85rem;
  }
</style>
