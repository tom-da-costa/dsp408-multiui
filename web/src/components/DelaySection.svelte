<script lang="ts">
  // Delay of one channel, in milliseconds and as a distance.
  import { app } from "../lib/app.svelte";
  import type { Channel } from "../lib/types";
  import Field from "./Field.svelte";
  import Section from "./Section.svelte";

  interface Props {
    channel: Channel;
    path: string;
    id?: string;
    title?: string;
  }

  let { channel, path, id = "delay", title = "Delay" }: Props = $props();

  const limits = $derived(app.hello?.limits);
  const maxMs = $derived(app.hello?.profile.delay_max_ms ?? 680);
  const editable = $derived(app.editable("delay_ms"));
</script>

<Section {id} {title} kind="delay_ms">
  {#if limits}
    {@const c = limits.speed_of_sound_m_s}
    <Field
      label="Delay"
      value={channel.delay_ms}
      min={0}
      max={maxMs}
      unit="ms"
      scale="sqrt"
      step={0.1}
      resolution={0.01}
      digits={2}
      disabled={!editable}
      onchange={(v) => app.set(`${path}.delay_ms`, v)}
    />
    <Field
      label="Distance"
      value={(channel.delay_ms * c) / 1000}
      min={0}
      max={(maxMs * c) / 1000}
      unit="m"
      step={0.1}
      resolution={0.01}
      digits={2}
      slider={false}
      disabled={!editable}
      onchange={(m) => app.set(`${path}.delay_ms`, (m * 1000) / c)}
    />
  {/if}
</Section>
