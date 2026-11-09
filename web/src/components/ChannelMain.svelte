<script lang="ts">
  // Gain, mute and phase of one channel, plus its name editor when `rename` is set.
  import { app } from "../lib/app.svelte";
  import { formatDb } from "../lib/scale";
  import type { Channel } from "../lib/types";
  import Field from "./Field.svelte";

  interface Props {
    channel: Channel;
    path: string;
    rename?: boolean;
  }

  let { channel, path, rename = false }: Props = $props();

  const limits = $derived(app.hello?.limits);

  // Channel name editing.
  let nameDraft = $state("");
  let nameFocused = $state(false);
  const nameLength = $derived(limits?.channel_name_length ?? 8);
  const nameValid = $derived(/^[\x20-\x7e]*$/.test(nameDraft) && nameDraft.length <= nameLength);
  const inputId = $derived(`name-${path}`);
  $effect(() => {
    // Follow the device's name unless the user is typing.
    const name = channel.name;
    if (!nameFocused) nameDraft = name;
  });

  async function saveName(event?: SubmitEvent) {
    event?.preventDefault();
    if (!nameValid || nameDraft === channel.name) return;
    await app.set(`${path}.name`, nameDraft);
    (document.activeElement as HTMLElement | null)?.blur();
  }
</script>

{#if limits}
  <Field
    label="Gain"
    value={channel.gain_db}
    min={limits.gain_db[0]}
    max={limits.gain_db[1]}
    unit="dB"
    step={0.5}
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
  <form class="rename" onsubmit={saveName}>
    <label for={inputId} class="muted">Name</label>
    <input
      id={inputId}
      type="text"
      maxlength={nameLength}
      autocomplete="off"
      enterkeyhint="done"
      bind:value={nameDraft}
      class:invalid={!nameValid}
      disabled={!app.editable("name")}
      onfocus={() => (nameFocused = true)}
      onblur={() => {
        nameFocused = false;
        void saveName();
      }}
    />
    <button
      type="submit"
      disabled={!app.editable("name") || !nameValid || nameDraft === channel.name}>Save</button
    >
  </form>
  <p class="hint muted">{nameLength} characters max, plain ASCII.</p>
{/if}

<style>
  .toggles {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin: 8px 0;
  }
  .rename {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 8px;
  }
  .rename input {
    min-height: 40px;
  }
  .rename input.invalid {
    border-color: var(--danger);
  }
  .hint {
    font-size: 0.8rem;
    margin: 6px 0 0;
  }
</style>
