<script lang="ts">
  // Name editor of one channel. Saves on Enter, on Save and on blur; Escape gives the device's
  // name back. `compact` drops the label and the hint (the All-in-one column header).
  import { onMount, tick } from "svelte";
  import { app } from "../lib/app.svelte";
  import type { Channel } from "../lib/types";

  interface Props {
    channel: Channel;
    path: string;
    compact?: boolean;
    /** Focus the field when shown. */
    autofocus?: boolean;
    /** Called once the edit is over (saved, unchanged or cancelled). */
    ondone?: () => void;
  }

  let { channel, path, compact = false, autofocus = false, ondone }: Props = $props();

  let draft = $state("");
  let focused = $state(false);
  let field: HTMLInputElement | undefined = $state();
  const maxLength = $derived(app.hello?.limits.channel_name_length ?? 8);
  const valid = $derived(/^[\x20-\x7e]*$/.test(draft) && draft.length <= maxLength);
  const inputId = $derived(`name-${path}${compact ? "-compact" : ""}`);

  $effect(() => {
    // Follow the device's name unless the user is typing.
    const name = channel.name;
    if (!focused) draft = name;
  });

  onMount(async () => {
    if (!autofocus) return;
    // Wait for the draft to reach the field, so that typing replaces the whole name.
    await tick();
    field?.focus();
    field?.select();
  });

  // Set by Escape so that the blur which follows does not save.
  let cancelled = false;

  /** Saves the draft if it changed. Every edit ends here, through the field's blur. */
  async function commit() {
    const name = draft;
    const changed = !cancelled && valid && name !== channel.name;
    cancelled = false;
    ondone?.();
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

<form class="rename" class:compact onsubmit={submit}>
  {#if !compact}<label for={inputId} class="muted">Name</label>{/if}
  <input
    id={inputId}
    bind:this={field}
    type="text"
    maxlength={maxLength}
    autocomplete="off"
    enterkeyhint="done"
    aria-label={compact ? "Channel name" : undefined}
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
{#if !compact}<p class="hint muted">{maxLength} characters max, plain ASCII.</p>{/if}

<style>
  .rename {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 8px;
  }
  .rename.compact {
    grid-template-columns: 1fr auto;
    gap: 4px;
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
