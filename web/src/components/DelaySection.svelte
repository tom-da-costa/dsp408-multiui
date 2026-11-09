<script lang="ts">
  // Delay of one channel, in milliseconds and as a distance.
  import { app } from "../lib/app.svelte";
  import { sampleStep } from "../lib/scale";
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
  // The DSP stores the delay in samples: − / + move by one sample (about 0.010 ms, 3.6 mm).
  const rate = $derived(app.hello?.profile.delay_sample_rate_hz ?? 96000);
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
      next={(v, d) => sampleStep(v, rate, d)}
      digits={3}
      disabled={!editable}
      onchange={(v) => app.set(`${path}.delay_ms`, v)}
    />
    <Field
      label="Distance"
      value={(channel.delay_ms * c) / 1000}
      min={0}
      max={(maxMs * c) / 1000}
      unit="m"
      next={(m, d) => (sampleStep((m * 1000) / c, rate, d) * c) / 1000}
      digits={3}
      slider={false}
      disabled={!editable}
      onchange={(m) => app.set(`${path}.delay_ms`, (m * 1000) / c)}
    />
  {/if}
</Section>
