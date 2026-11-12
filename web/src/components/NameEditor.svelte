<script lang="ts">
  // Name editor of one channel. Saves on Enter, on Save and on blur; Escape gives the device's
  // name back. `label` is shown before the field ("Name"; a slot such as "Out 5" in a merged
  // link group); empty, the field has none (it sits in a "Name" section). `hint: false` leaves
  // out the length hint, for a list of fields that shows it once.
  import { app } from "../lib/app.svelte";
  import type { Channel } from "../lib/types";

  interface Props {
    channel: Channel;
    path: string;
    label?: string;
    hint?: boolean;
  }

  let { channel, path, label = "Name", hint = true }: Props = $props();

  let draft = $state("");
  let focused = $state(false);
  let field: HTMLInputElement | undefined = $state();
  const maxLength = $derived(app.hello?.limits.channel_name_length ?? 8);
  const valid = $derived(/^[\x20-\x7e]*$/.test(draft) && draft.length <= maxLength);
  const inputId = $derived(`name-${path}`);

  $effect(() => {
    // Follow the device's name unless the user is typing.
    const name = channel.name;
    if (!focused) draft = name;
  });

  // Set by Escape so that the blur which follows does not save.
  let cancelled = false;

  /** Saves the draft if it changed. Every edit ends here, through the field's blur. */
  async function commit() {
    const name = draft;
    const changed = !cancelled && valid && name !== channel.name;
    cancelled = false;
    if (changed) await app.set(`${path}.name`, name);
  }

  function submit(event: SubmitEvent) {
    event.preventDefault();
    if (document.activeElement === field) field?.blur();
    else void commit();
  }

  function onkeydown(event: KeyboardEvent) {
    if (event.key !== "Escape") return;
    cancelled = true;
    draft = channel.name;
    field?.blur();
  }
</script>

<form class="rename" class:bare={!label} onsubmit={submit}>
  {#if label}<label for={inputId} class="muted">{label}</label>{/if}
  <input
    id={inputId}
    bind:this={field}
    type="text"
    maxlength={maxLength}
    autocomplete="off"
    enterkeyhint="done"
    aria-label={label ? undefined : "Channel name"}
    bind:value={draft}
    class:invalid={!valid}
    disabled={!app.editable("name")}
    onfocus={() => (focused = true)}
    onblur={() => {
      focused = false;
      void commit();
    }}
    {onkeydown}
  />
  <button type="submit" disabled={!app.editable("name") || !valid || draft === channel.name}
    >Save</button
  >
</form>
{#if hint}<p class="hint muted">{maxLength} characters max, plain ASCII.</p>{/if}

<style>
  .rename {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 8px;
  }
  .rename.bare {
    grid-template-columns: 1fr auto;
  }
  .rename input {
    min-height: 40px;
    min-width: 0;
  }
  .rename input.invalid {
    border-color: var(--danger);
  }
  .hint {
    font-size: 0.8rem;
    margin: 6px 0 0;
  }
</style>
