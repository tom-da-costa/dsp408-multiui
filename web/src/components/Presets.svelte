<script lang="ts">
  import { app } from "../lib/app.svelte";

  const device = $derived(app.device);
  let storing = $state<number | null>(null);
  let name = $state("");
  let busy = $state(false);

  const nameError = $derived(
    name.length === 0
      ? "a name is required"
      : name.length > 14
        ? "14 characters at most"
        : /^[\x20-\x7e]*$/.test(name)
          ? ""
          : "plain ASCII characters only",
  );

  function label(slot: number): string {
    return slot === 0 ? "F00" : `U${String(slot).padStart(2, "0")}`;
  }

  async function recall(slot: number, presetName: string) {
    const lost =
      device?.modified === true
        ? "\n\nThe current setup has UNSAVED CHANGES: they will be lost."
        : device?.modified === null
          ? "\n\nChanges made before this app connected, if any, will be lost."
          : "";
    if (!confirm(`Recall ${label(slot)} "${presetName}"? Every current setting is replaced.${lost}`))
      return;
    busy = true;
    if (await app.run({ type: "preset.recall", slot })) app.toast(`${label(slot)} recalled`);
    busy = false;
  }

  function startStore(slot: number, current: string) {
    storing = slot;
    name = current === "Default Preset" ? (device?.preset_name ?? "") : current;
  }

  async function store(event: SubmitEvent) {
    event.preventDefault();
    if (storing === null || nameError) return;
    busy = true;
    if (await app.run({ type: "preset.store", slot: storing, name })) {
      app.toast(`Stored to ${label(storing)}`);
      storing = null;
    }
    busy = false;
  }
</script>

{#if device}
  <div class="card">
    <h2>Presets</h2>
    <p class="live">
      <span class="muted">Live: {label(device.active_slot)} — {device.preset_name}</span>
      {#if device.modified}
        <span class="unsaved">● unsaved changes</span>
        {#if device.active_slot > 0}
          <button
            class="primary"
            disabled={app.readOnly || busy}
            onclick={() => startStore(device.active_slot, device.preset_name)}
            >Save to {label(device.active_slot)}</button
          >
        {/if}
      {/if}
    </p>
    <ul>
      <li class:active={device.active_slot === 0}>
        <span class="slot">F00</span><span class="name">Factory default</span>
        <button disabled={app.readOnly || busy} onclick={() => recall(0, "Factory default")}
          >Recall</button
        >
        <span class="spacer"></span>
      </li>
      {#each device.presets as preset (preset.slot)}
        <li class:active={device.active_slot === preset.slot}>
          <span class="slot">{label(preset.slot)}</span>
          <span class="name">{preset.name}</span>
          <button disabled={app.readOnly || busy} onclick={() => recall(preset.slot, preset.name)}
            >Recall</button
          >
          <button
            disabled={app.readOnly || busy}
            onclick={() => startStore(preset.slot, preset.name)}>Store</button
          >
        </li>
      {/each}
    </ul>
  </div>

  {#if storing !== null}
    <div class="backdrop" role="presentation" onclick={() => (storing = null)}></div>
    <form class="card dialog" onsubmit={store}>
      <h2>Store to {label(storing)}</h2>
      <p class="muted">This overwrites the preset stored in the DSP.</p>
      <label>
        Name
        <input type="text" maxlength="14" bind:value={name} />
      </label>
      {#if nameError}<p class="error">{nameError}</p>{/if}
      <div class="actions">
        <button type="button" onclick={() => (storing = null)}>Cancel</button>
        <button class="primary" type="submit" disabled={!!nameError || busy}>Store</button>
      </div>
    </form>
  {/if}
{/if}

<style>
  /* Buttons stay next to the name (no wide gap on a desktop) and rows are separated, so it is
     clear which preset a Recall / Store button belongs to. */
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    max-width: 560px;
  }
  li {
    display: grid;
    /* fixed button columns: every row lines up, F00 (no Store) included */
    grid-template-columns: 3.2em minmax(0, 1fr) 5.4em 5.4em;
    gap: 8px;
    align-items: center;
    padding: 6px;
    border-bottom: 1px solid var(--line);
  }
  li:last-child {
    border-bottom: none;
  }
  li > button {
    padding: 0 8px;
  }
  /* Narrow (phone): the full name on the first line, the buttons right under it. */
  ul {
    container-type: inline-size;
  }
  @container (max-width: 380px) {
    li {
      grid-template-columns: 3.2em 1fr 5.4em 5.4em;
      grid-template-areas: "slot name name name" ". . recall store";
      row-gap: 4px;
    }
    li > .slot {
      grid-area: slot;
    }
    li > .name {
      grid-area: name;
      white-space: normal;
    }
    li > button:nth-of-type(1) {
      grid-area: recall;
    }
    li > button:nth-of-type(2),
    li > .spacer {
      grid-area: store;
    }
  }
  li:nth-child(even):not(.active) {
    background: rgba(255, 255, 255, 0.025);
  }
  li:hover:not(.active) {
    background: rgba(255, 255, 255, 0.06);
  }
  li.active {
    background: rgba(61, 220, 151, 0.12);
    outline: 1px solid var(--accent);
    outline-offset: -1px;
    border-radius: 6px;
  }
  .slot {
    font-variant-numeric: tabular-nums;
    color: var(--muted);
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    z-index: 10;
  }
  .dialog {
    position: fixed;
    z-index: 11;
    left: 50%;
    top: 20%;
    transform: translateX(-50%);
    width: min(360px, calc(100% - 32px));
    display: grid;
    gap: 12px;
  }
  .dialog label {
    display: grid;
    gap: 6px;
  }
  .actions {
    display: flex;
    gap: 8px;
    justify-content: flex-end;
  }
  .error {
    color: var(--danger);
    margin: 0;
  }
  .live {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px 12px;
  }
  .unsaved {
    color: var(--warn);
    font-weight: 600;
  }
</style>
