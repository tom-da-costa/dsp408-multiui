<script lang="ts">
  // One setting of one channel, as a collapsible section. Renders nothing when the setting
  // does not exist on that channel (a gate on an output, a compressor on an input…).
  import { app } from "../lib/app.svelte";
  import type { Param } from "../lib/nav.svelte";
  import type { InputChannel, OutputChannel } from "../lib/types";
  import ChannelMain from "./ChannelMain.svelte";
  import CrossoverSection from "./CrossoverSection.svelte";
  import DelaySection from "./DelaySection.svelte";
  import DynamicsSection from "./DynamicsSection.svelte";
  import GeqSection from "./GeqSection.svelte";
  import PeqSection from "./PeqSection.svelte";
  import RoutingSection from "./RoutingSection.svelte";
  import Section from "./Section.svelte";

  interface Props {
    param: Param;
    path: string;
    title?: string;
  }

  let { param, path, title }: Props = $props();

  const isOutput = $derived(path.startsWith("outputs."));
  const index = $derived(Number(path.split(".")[1]));
  const input = $derived(
    isOutput ? undefined : (app.device?.inputs[index] as InputChannel | undefined),
  );
  const output = $derived(
    isOutput ? (app.device?.outputs[index] as OutputChannel | undefined) : undefined,
  );
  const channel = $derived(input ?? output);
  const id = $derived(`${param}@${path}`);
</script>

{#if channel}
  {#if param === "gain"}
    <Section {id} title={title ?? "Gain"}><ChannelMain {channel} {path} /></Section>
  {:else if param === "delay"}
    <DelaySection {channel} {path} {id} {title} />
  {:else if param === "eq"}
    <PeqSection {channel} {path} {id} {title} />
  {:else if param === "filters"}
    <CrossoverSection {channel} {path} {id} {title} />
  {:else if param === "comp" && output}
    <DynamicsSection
      kind="compressor"
      {path}
      values={{ ...output.compressor }}
      reduction={app.meters?.comp?.[index] ?? null}
      {id}
      {title}
    />
  {:else if param === "limit" && output}
    <DynamicsSection
      kind="limiter"
      {path}
      values={{ ...output.limiter }}
      reduction={app.meters?.limit?.[index] ?? null}
      {id}
      {title}
    />
  {:else if param === "gate" && input}
    <DynamicsSection kind="gate" {path} values={{ ...input.gate }} {id} {title} />
  {:else if param === "geq" && input}
    <GeqSection channel={input} {path} {id} {title} />
  {:else if param === "matrix" && output}
    <RoutingSection channel={output} {path} {id} {title} />
  {/if}
{/if}
