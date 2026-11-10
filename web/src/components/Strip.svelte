<script lang="ts">
  import { app } from "../lib/app.svelte";
  import { nav, slotLabel } from "../lib/nav.svelte";
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

<section class="strip" class:muted={channel.mute} style:--ch={app.color(path)}>
  <button
    class="name"
    title={`${slotLabel(path)} ${channel.name}: open the channel settings`}
    onclick={() => nav.open(path)}
  >
    <span class="slot"
      >{slotLabel(path)}{#if channel.linked.length}<span
          class="link"
          title="Linked: changes also apply to the other channels of the group">🔗</span
        >{/if}</span
    >
    <span class="label">{channel.name || "—"}</span>
  </button>
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
  .name {
    border: 2px solid var(--ch);
    color: var(--ch);
    display: grid;
    min-height: 40px;
    padding: 2px 4px;
    line-height: 1.15;
    text-align: center;
    min-width: 0;
  }
  .name span {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .slot {
    font-size: 0.7rem;
    color: inherit;
  }
  .link {
    margin-left: 2px;
    font-size: 0.6rem;
  }
  .label {
    font-weight: 600;
    font-size: 0.85rem;
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
  .strip.muted {
    /* Muted: a thick red frame and a reddened background (the name keeps its channel colour,
       which can itself be red). An inset shadow, so the strip keeps its size. */
    border-color: var(--danger);
    box-shadow: inset 0 0 0 2px var(--danger);
    background: color-mix(in srgb, var(--danger) 14%, var(--panel));
  }
</style>
