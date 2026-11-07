<script lang="ts">
  import { app } from "../lib/app.svelte";
  import type { Channel } from "../lib/types";
  import Fader from "./Fader.svelte";
  import Meter from "./Meter.svelte";

  interface Props {
    channel: Channel;
    path: string; // "inputs.0" / "outputs.3"
    meterIndex: number;
    outputIndex: number | null; // index among outputs, for LIM/COMP flags
  }

  let { channel, path, meterIndex, outputIndex }: Props = $props();

  const meters = $derived(app.meters);
  const level = $derived(meters?.levels ? (meters.levels[meterIndex] ?? null) : null);
  const clip = $derived(meters?.clip?.[meterIndex] ?? false);
  const limit = $derived(
    outputIndex === null ? null : meters?.limit ? (meters.limit[outputIndex] ?? false) : null,
  );
  const comp = $derived(
    outputIndex === null ? null : meters?.comp ? (meters.comp[outputIndex] ?? false) : null,
  );
  const floor = $derived(app.hello?.profile.meter_floor_db ?? -90);
</script>

<section class="strip" class:muted={channel.mute}>
  <header title={channel.name}>{channel.name || "—"}</header>
  <div class="body">
    <Meter {level} {clip} {limit} {comp} {floor} />
    <Fader
      value={channel.gain_db}
      label={channel.name}
      disabled={app.readOnly}
      onchange={(db) => app.set(`${path}.gain_db`, db)}
    />
  </div>
  <div class="buttons">
    <button
      class="mute"
      class:on={channel.mute}
      disabled={app.readOnly}
      aria-pressed={channel.mute}
      onclick={() => app.set(`${path}.mute`, !channel.mute)}>MUTE</button
    >
    <button
      class="phase"
      class:on={channel.phase}
      disabled={app.readOnly}
      aria-pressed={channel.phase}
      title="Phase invert"
      onclick={() => app.set(`${path}.phase`, !channel.phase)}>Ø</button
    >
  </div>
</section>

<style>
  .strip {
    flex: 1 0 80px;
    max-width: 120px;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 8px 4px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius);
  }
  header {
    text-align: center;
    font-weight: 600;
    font-size: 0.85rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .body {
    flex: 1;
    display: flex;
    gap: 4px;
    justify-content: center;
    min-height: 0;
  }
  .buttons {
    display: grid;
    gap: 6px;
  }
  .buttons button {
    padding: 0;
    font-weight: 700;
    font-size: 0.8rem;
  }
  .mute.on {
    background: var(--danger);
    border-color: var(--danger);
    color: #fff;
  }
  .phase.on {
    background: var(--info);
    border-color: var(--info);
    color: #000;
  }
  .strip.muted header {
    color: var(--danger);
  }
</style>
