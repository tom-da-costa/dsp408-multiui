<script lang="ts">
  import { app } from "../lib/app.svelte";
  import { links } from "../lib/links.svelte";
  import { nav } from "../lib/nav.svelte";
  import type { Channel } from "../lib/types";
  import Fader from "./Fader.svelte";
  import Meter from "./Meter.svelte";

  interface Props {
    channel: Channel;
    path: string; // "inputs.0" / "outputs.3"
  }

  let { channel, path }: Props = $props();

  // Merged over the link group when "Merge linked channels" is on.
  const meter = $derived(links.meter(path));
  const level = $derived(meter.level);
  const clip = $derived(meter.clip);
  const limit = $derived(meter.limit);
  const comp = $derived(meter.comp);
  const floor = $derived(app.hello?.profile.meter_floor_db ?? -90);
</script>

<section class="strip" class:muted={channel.mute} style:--ch={app.color(path)}>
  <button
    class="name"
    title={`${links.slot(path)} ${links.name(path)}: open the channel settings`}
    onclick={() => nav.open(path)}
  >
    <span class="slot"
      >{links.slot(path)}{#if links.mark(path)}<span
          class="link"
          title="Linked: changes also apply to the other channels of the group">🔗</span
        >{/if}</span
    >
    <span class="label">{links.name(path)}</span>
  </button>
  <div class="body">
    <Meter {level} {clip} {limit} {comp} {floor} />
    <Fader
      value={channel.gain_db}
      label={links.name(path)}
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
    /* No shrinking below the fader's own height: it would overflow under MUTE and hide −. */
    flex: 1;
    display: flex;
    gap: 4px;
    justify-content: center;
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
    /* Muted: red diagonal hatching (the name keeps its channel colour, which can itself be
       red). */
    background-image: repeating-linear-gradient(
      -45deg,
      rgb(255 77 94 / 0.3) 0 4px, /* --danger at 30 % */
      transparent 4px 16px
    );
  }
</style>
