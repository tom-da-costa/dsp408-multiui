<script lang="ts">
  // Every setting of one channel (the "Channels" tab).
  import { app } from "../lib/app.svelte";
  import { links } from "../lib/links.svelte";
  import { slotLabel } from "../lib/nav.svelte";
  import type { InputChannel, OutputChannel } from "../lib/types";
  import ChannelMain from "./ChannelMain.svelte";
  import CrossoverSection from "./CrossoverSection.svelte";
  import DelaySection from "./DelaySection.svelte";
  import DynamicsSection from "./DynamicsSection.svelte";
  import GeqSection from "./GeqSection.svelte";
  import LevelBar from "./LevelBar.svelte";
  import NameEditor from "./NameEditor.svelte";
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
  /** The channels shown here: the whole link group with "Merge linked channels". */
  const members = $derived(links.members(path));
  const merged = $derived(members.length > 1);
  function outputAt(member: string): OutputChannel | undefined {
    return device?.outputs[Number(member.split(".")[1])];
  }
  function channelAt(member: string) {
    const n = Number(member.split(".")[1]);
    return isOutput ? device?.outputs[n] : device?.inputs[n];
  }
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
      <h2 style:--ch={app.color(path)}>
        {links.slot(path)} <span class="name">{links.name(path)}</span>
      </h2>
      <LevelBar {path} indicators />
    </div>

    {#if merged}
      <p class="linked">
        🔗 Linked channels, shown as one: every change applies to all of them (the DSP does it),
        except the name and the routing, set per channel below.
      </p>
    {:else if channel.linked.length}
      <p class="linked">
        🔗 Linked with {linkedNames}: the DSP applies every change except the name and the
        routing to {channel.linked.length > 1 ? "them" : "it"} too.
      </p>
    {/if}

    <ResponseGraph {path} />

    <div class="sections">
      <Section id="channel" title="Channel">
        <ChannelMain {channel} {path} rename={!merged} />
        {#if merged}
          {#each members as member (member)}
            {@const memberChannel = channelAt(member)}
            {#if memberChannel}
              <NameEditor channel={memberChannel} path={member} label={slotLabel(member)} />
            {/if}
          {/each}
        {/if}
      </Section>
      <DelaySection {channel} {path} />
      {#if output}
        {#each members as member (member)}
          {@const memberOutput = outputAt(member)}
          {#if memberOutput}
            <RoutingSection
              channel={memberOutput}
              path={member}
              id={merged ? `routing@${member}` : "routing"}
              title={merged ? `Routing · ${slotLabel(member)}` : "Routing"}
            />
          {/if}
        {/each}
      {/if}
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
  h2 .name {
    font-weight: 400;
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
