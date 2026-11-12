<script lang="ts">
  // "Params" tab: one sub-tab per setting, each showing that setting on the channels picked in
  // the row below (as in Live and All-in-one; one choice for every setting, remembered in
  // this browser). Link and Matrix have tabs of their own.
  import { app } from "../lib/app.svelte";
  import { links } from "../lib/links.svelte";
  import { nav, PARAM_SCOPE, PARAM_TABS } from "../lib/nav.svelte";
  import { ChannelSelection } from "../lib/selection.svelte";
  import ChannelPicker from "./ChannelPicker.svelte";
  import ChipBar from "./ChipBar.svelte";
  import Mixer from "./Mixer.svelte";
  import ParamBlock from "./ParamBlock.svelte";
  import ParamStrips from "./ParamStrips.svelte";
  import ResponseGraph from "./ResponseGraph.svelte";

  // Settings shown as one strip per channel, like the mixer; EQ as one response graph per
  // channel (bands dragged on it) with its band list (type, on / off, values); GEQ as cards.
  const STRIPS = new Set(["delay", "filters", "comp", "limit", "gate"]);

  const selection = new ChannelSelection("dsp408.params.hidden");
  const scope = $derived(PARAM_SCOPE[nav.param]);
  /** The setting exists on one side only (compressor on outputs, gate on inputs…). */
  const side = $derived(scope === "all" ? undefined : scope);
  const paths = $derived(selection.shown.filter((p) => !side || p.startsWith(`${side}.`)));

  function title(path: string): string {
    return `${links.slot(path)} · ${links.name(path)}${links.mark(path)}`;
  }
</script>

<ChipBar
  items={PARAM_TABS.map(([key, label]) => ({ key, label }))}
  selected={nav.param}
  onselect={(k) => nav.selectParam(k as typeof nav.param)}
  label="Setting"
/>

{#if nav.param === "gain"}
  <Mixer {selection} {paths} />
{:else if nav.param === "eq"}
  <ChannelPicker {selection} />
  <div class="graphs">
    {#each paths as path (path)}
      <div class="graph-block" style:--ch={app.color(path)}>
        <ResponseGraph {path} compact title={title(path)} />
        <ParamBlock param="eq" {path} />
      </div>
    {:else}
      <p class="muted">No channel selected: pick some above.</p>
    {/each}
  </div>
{:else}
  {#if STRIPS.has(nav.param)}
    <ParamStrips param={nav.param} {paths} {selection} {side} />
  {:else}
    <ChannelPicker {selection} {side} />
    <div class="cards">
      {#each paths as path (path)}
        <div class="block" style:--ch={app.color(path)}>
          <ParamBlock param={nav.param} {path} title={title(path)} />
        </div>
      {:else}
        <p class="muted">No channel selected: pick some above.</p>
      {/each}
    </div>
  {/if}
{/if}

<style>
  .graphs {
    /* one graph per row, the whole width */
    display: grid;
    gap: 10px;
  }
  .graph-block {
    display: grid;
    gap: 6px;
  }
  .graph-block > :global(.card) {
    margin: 0;
  }
  /* The band list in columns: the graph above takes the whole width. */
  .graph-block :global(ol.bands) {
    grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr));
    align-items: start;
  }
  .graph-block > :global(.graph h2) {
    padding: 2px 10px;
    border: 2px solid var(--ch);
    border-radius: var(--radius);
    color: var(--ch);
  }
  .cards {
    columns: 3 360px;
    column-gap: 10px;
  }
  .block {
    break-inside: avoid;
  }
  .block > :global(.card .title) {
    margin: 6px 0;
    padding: 4px 10px;
    border: 2px solid var(--ch);
    border-radius: var(--radius);
    color: var(--ch);
  }
</style>
