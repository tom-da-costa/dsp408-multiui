<script lang="ts">
  // "Params" tab: one sub-tab per setting, each showing that setting on the channels picked in
  // the row below (as in Live and All-in-one; one choice for every setting, remembered in
  // this browser).
  import { app } from "../lib/app.svelte";
  import { links } from "../lib/links.svelte";
  import { nav, PARAM_SCOPE, PARAMS } from "../lib/nav.svelte";
  import { ChannelSelection } from "../lib/selection.svelte";
  import ChannelPicker from "./ChannelPicker.svelte";
  import ChipBar from "./ChipBar.svelte";
  import LinkEditor from "./LinkEditor.svelte";
  import Matrix from "./Matrix.svelte";
  import Mixer from "./Mixer.svelte";
  import ParamBlock from "./ParamBlock.svelte";
  import ParamStrips from "./ParamStrips.svelte";

  // Settings shown as one strip per channel, like the mixer; the others (EQ, GEQ) as cards.
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
  items={PARAMS.map(([key, label]) => ({ key, label }))}
  selected={nav.param}
  onselect={(k) => nav.selectParam(k as typeof nav.param)}
  label="Setting"
/>

{#if nav.param === "gain"}
  <Mixer {selection} {paths} />
{:else if nav.param === "matrix"}
  <Matrix />
{:else if nav.param === "link"}
  <LinkEditor />
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
