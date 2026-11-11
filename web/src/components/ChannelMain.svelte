<script lang="ts">
  // Gain, mute and phase of one channel, plus its name editor when `rename` is set.
  import { app } from "../lib/app.svelte";
  import { formatDb, gainStep } from "../lib/scale";
  import type { Channel } from "../lib/types";
  import Field from "./Field.svelte";
  import NameEditor from "./NameEditor.svelte";

  interface Props {
    channel: Channel;
    path: string;
    rename?: boolean;
  }

  let { channel, path, rename = false }: Props = $props();

  const limits = $derived(app.hello?.limits);
</script>

{#if limits}
  <Field
    label="Gain"
    value={channel.gain_db}
    min={limits.gain_db[0]}
    max={limits.gain_db[1]}
    unit="dB"
    next={gainStep}
    resolution={0.1}
    origin={0}
    format={(v) => formatDb(v)}
    disabled={!app.editable("gain_db")}
    onchange={(v) => app.set(`${path}.gain_db`, v)}
  />
{/if}
<div class="toggles">
  <button
    class="switch danger"
    class:on={channel.mute}
    disabled={!app.editable("mute")}
    aria-pressed={channel.mute}
    onclick={() => app.set(`${path}.mute`, !channel.mute)}>Mute</button
  >
  <button
    class="switch"
    class:on={channel.phase}
    disabled={!app.editable("phase")}
    aria-pressed={channel.phase}
    title="Phase invert"
    onclick={() => app.set(`${path}.phase`, !channel.phase)}>Ø Phase</button
  >
</div>
{#if rename}
  <NameEditor {channel} {path} />
{/if}

<style>
  .toggles {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin: 8px 0;
  }
</style>
