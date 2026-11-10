<script lang="ts">
  // Asks for the access code to unlock the screen (opened from the rail's "Unlock screen").
  // No backdrop: the screen stays readable behind it.
  import { app } from "../lib/app.svelte";

  interface Props {
    onclose: () => void;
  }

  let { onclose }: Props = $props();

  let pin = $state("");
  let error = $state("");
  let busy = $state(false);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = (await app.unlockScreen(pin)) ?? "";
    busy = false;
    pin = "";
    if (!error) onclose();
  }
</script>

<svelte:window onkeydown={(e) => e.key === "Escape" && onclose()} />

<div class="anchor">
  <form class="card" onsubmit={submit} aria-label="Unlock the screen">
    <p>Type the access code to unlock the screen.</p>
    <!-- svelte-ignore a11y_autofocus -->
    <input
      type="password"
      inputmode="numeric"
      autocomplete="off"
      aria-label="Access code"
      bind:value={pin}
      autofocus
      required
    />
    {#if error}<p class="error" role="alert">{error}</p>{/if}
    <div class="buttons">
      <button type="button" onclick={onclose}>Cancel</button>
      <button class="primary" type="submit" disabled={busy || !pin || !app.connected}>Unlock</button>
    </div>
  </form>
</div>

<style>
  .anchor {
    position: fixed;
    left: 50%;
    top: 16px;
    transform: translateX(-50%);
    z-index: 100;
    width: min(320px, calc(100vw - 32px));
  }
  form {
    display: grid;
    gap: 10px;
    border-color: var(--warn);
    box-shadow: 0 8px 30px rgb(0 0 0 / 0.5);
  }
  p {
    margin: 0;
  }
  .error {
    color: var(--danger);
  }
  .buttons {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
</style>
