<script lang="ts">
  import { LoginError } from "../lib/api";
  import { app } from "../lib/app.svelte";

  let pin = $state("");
  let name = $state(localStorageGet("dsp408.name"));
  let error = $state("");
  let busy = $state(false);

  function localStorageGet(key: string): string {
    try {
      return localStorage.getItem(key) ?? "";
    } catch {
      return "";
    }
  }

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = "";
    app.loginNotice = "";
    try {
      try {
        localStorage.setItem("dsp408.name", name);
      } catch {
        /* private mode: the name is just not remembered */
      }
      await app.login(pin, name.trim());
    } catch (exc) {
      error = exc instanceof LoginError ? exc.message : "cannot reach the server";
      pin = "";
    } finally {
      busy = false;
    }
  }
</script>

<main>
  <form class="card" onsubmit={submit}>
    <h1>t.racks DSP controller</h1>
    <label>
      Access code
      <input
        type="password"
        inputmode="numeric"
        autocomplete="current-password"
        bind:value={pin}
        required
      />
    </label>
    <label>
      Your name <span class="muted">(optional)</span>
      <input type="text" maxlength="32" placeholder="e.g. FOH phone" bind:value={name} />
    </label>
    {#if app.loginNotice}<p class="notice" role="status">{app.loginNotice}</p>{/if}
    {#if error}<p class="error" role="alert">{error}</p>{/if}
    <button class="primary" type="submit" disabled={busy || !pin}>Connect</button>
  </form>
</main>

<style>
  .notice {
    margin: 0;
    padding: 8px 10px;
    border-radius: 8px;
    background: color-mix(in srgb, var(--warn) 18%, var(--panel));
    border-left: 3px solid var(--warn);
  }
  main {
    min-height: 100%;
    display: grid;
    place-items: center;
    padding: 16px;
  }
  form {
    width: min(360px, 100%);
    display: grid;
    gap: 14px;
  }
  h1 {
    margin: 0;
    font-size: 1.4rem;
  }
  label {
    display: grid;
    gap: 6px;
  }
  .error {
    color: var(--danger);
    margin: 0;
  }
</style>
