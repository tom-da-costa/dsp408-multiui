<script lang="ts">
  // Every setting of one channel (the "Channels" tab).
  import { app } from "../lib/app.svelte";
  import { slotLabel } from "../lib/nav.svelte";
  import type { InputChannel, OutputChannel } from "../lib/types";
  import ChannelMain from "./ChannelMain.svelte";
  import CrossoverSection from "./CrossoverSection.svelte";
  import DelaySection from "./DelaySection.svelte";
  import DynamicsSection from "./DynamicsSection.svelte";
  import GeqSection from "./GeqSection.svelte";
  import LevelBar from "./LevelBar.svelte";
  import PeqSection from "./PeqSection.svelte";
  import ResponseGraph from "./ResponseGraph.svelte";
  import RoutingSection from "./RoutingSection.svelte";
  import Section from "./Section.svelte";

  interface Props {
    path: string; // "inputs.0" / "outputs.3"
  }

  let { path }: Props = $props();

  const isOutput = $derived(path.startsWith("outputs."));
  const index = $derived(Number(path.split(".")[1]));
  const device = $derived(app.device);
  const input = $derived(isOutput ? undefined : (device?.inputs[index] as InputChannel | undefined));
  const output = $derived(isOutput ? (device?.outputs[index] as OutputChannel | undefined) : undefined);
  const channel = $derived(input ?? output);
  const limit = $derived(isOutput ? (app.meters?.limit?.[index] ?? null) : null);
  const comp = $derived(isOutput ? (app.meters?.comp?.[index] ?? null) : null);
  const linkedNames = $derived(
    (channel?.linked ?? [])
      .map((i) => slotLabel(`${isOutput ? "outputs" : "inputs"}.${i}`))
      .join(", "),
  );
</script>

{#if !channel}
  <p class="muted">No such channel.</p>
{:else}
  <div class="detail">
    <div class="top">
      <h2 style:--ch={app.color(path)}>{slotLabel(path)} <span class="muted">{channel.name}</span></h2>
      <LevelBar {path} />
    </div>

    {#if channel.linked.length}
      <p class="linked">
        🔗 Linked with {linkedNames}: the DSP applies every change except the name and the
        routing to {channel.linked.length > 1 ? "them" : "it"} too.
      </p>
    {/if}

    <ResponseGraph {path} />

    <div class="sections">
      <Section id="channel" title="Channel">
        <ChannelMain {channel} {path} rename />
      </Section>
      <DelaySection {channel} {path} />
      {#if output}<RoutingSection channel={output} {path} />{/if}
      <CrossoverSection {channel} {path} />
      <PeqSection {channel} {path} />
      {#if output}
        <DynamicsSection kind="compressor" {path} values={{ ...output.compressor }} reduction={comp} />
        <DynamicsSection kind="limiter" {path} values={{ ...output.limiter }} reduction={limit} />
      {/if}
      {#if input}
        <DynamicsSection kind="gate" {path} values={{ ...input.gate }} />
        <GeqSection channel={input} {path} />
      {/if}
    </div>
  </div>
{/if}

<style>
  .detail {
    max-width: 1200px;
    margin: 0 auto;
  }
  .top {
    display: grid;
    gap: 8px;
    margin-bottom: 10px;
  }
  h2 {
    margin: 0;
    justify-self: start;
    max-width: 100%;
    padding: 2px 12px;
    border: 2px solid var(--ch);
    border-radius: var(--radius);
    color: var(--ch);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .linked {
    margin: -4px 0 10px;
    padding: 8px 10px;
    border-radius: 6px;
    background: var(--panel-2);
    font-size: 0.85rem;
  }
  .sections {
    columns: 2 420px;
    column-gap: 10px;
  }
</style>
