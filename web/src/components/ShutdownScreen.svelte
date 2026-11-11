<script lang="ts">
  // Shown to every client once the server was shut down from Settings ("Disconnect from DSP
  // and shutdown"): the app stops trying to reconnect until the page is reloaded.
  import { app } from "../lib/app.svelte";
</script>

<main>
  <section class="card" role="status">
    <h1>Server shut down</h1>
    <p>
      {app.shutdownBy || "Someone"} disconnected the server from the DSP and shut it down. The
      DSP keeps its current settings and is free for another program (such as the t.racks
      editor).
    </p>
    <p class="muted">Start the server again, then reload this page.</p>
    <button class="primary" onclick={() => location.reload()}>Reload</button>
  </section>
</main>

<style>
  main {
    min-height: 100%;
    display: grid;
    place-items: center;
    padding: 16px;
    box-sizing: border-box;
  }
  section {
    max-width: 420px;
    display: grid;
    gap: 10px;
  }
  h1 {
    margin: 0;
    font-size: 1.3rem;
  }
  p {
    margin: 0;
  }
</style>
