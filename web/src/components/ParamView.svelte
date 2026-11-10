<script lang="ts">
  // "Params" tab: one sub-tab per setting, each showing that setting on every channel.
  import { app } from "../lib/app.svelte";
  import { nav, PARAM_SCOPE, PARAMS, SIDES, slotLabel } from "../lib/nav.svelte";
  import ChipBar from "./ChipBar.svelte";
  import LinkEditor from "./LinkEditor.svelte";
  import Matrix from "./Matrix.svelte";
  import Mixer from "./Mixer.svelte";
  import ParamBlock from "./ParamBlock.svelte";

  const device = $derived(app.device);
  const scope = $derived(PARAM_SCOPE[nav.param]);
  const paths = $derived(
    [
      ...(device?.inputs ?? []).map((c, i) => [`inputs.${i}`, c.name] as const),
      ...(device?.outputs ?? []).map((c, i) => [`outputs.${i}`, c.name] as const),
    ].filter(([path]) => {
      const kind = path.startsWith("inputs.") ? "inputs" : "outputs";
      return (scope === "all" || scope === kind) && (nav.side === "all" || nav.side === kind);
    }),
  );

  function title(path: string, name: string): string {
    const index = Number(path.split(".")[1]);
    const channel = path.startsWith("inputs.") ? device?.inputs[index] : device?.outputs[index];
    return `${slotLabel(path)} · ${name || "—"}${channel?.linked.length ? " 🔗" : ""}`;
  }
</script>

<ChipBar
  items={PARAMS.map(([key, label]) => ({ key, label }))}
  selected={nav.param}
  onselect={(k) => nav.selectParam(k as typeof nav.param)}
  label="Setting"
/>

{#if nav.param === "gain"}
  <Mixer />
{:else if nav.param === "matrix"}
  <Matrix />
{:else if nav.param === "link"}
  <LinkEditor />
{:else}
  {#if scope === "all"}
    <ChipBar
      items={SIDES.map(([key, label]) => ({ key, label }))}
      selected={nav.side}
      onselect={(k) => (nav.side = k as typeof nav.side)}
      label="Channels shown"
    />
  {/if}
  <div class="cards">
    {#each paths as [path, name] (path)}
      <ParamBlock param={nav.param} {path} title={title(path, name)} />
    {/each}
  </div>
{/if}

<style>
  .cards {
    columns: 3 360px;
    column-gap: 10px;
  }
</style>
