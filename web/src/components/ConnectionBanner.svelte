<script lang="ts">
  // Banner above every tab when a link is down: this browser ↔ the server, or the server ↔ the
  // DSP. Values on screen are then the last known ones and every control is disabled. A short
  // grace delay keeps a quick reconnection (a missed update, one lost reply) from flashing it.
  import { app } from "../lib/app.svelte";

  const GRACE_MS = 1_500;

  const serverDown = $derived(!app.connected);
  const dspDown = $derived(app.connected && app.status !== null && app.status.status !== "online");

  let showServer = $state(false);
  let showDsp = $state(false);

  $effect(() => {
    if (!serverDown) {
      showServer = false;
      return;
    }
    const timer = setTimeout(() => (showServer = true), GRACE_MS);
    return () => clearTimeout(timer);
  });

  $effect(() => {
    if (!dspDown) {
      showDsp = false;
      return;
    }
    const timer = setTimeout(() => (showDsp = true), GRACE_MS);
    return () => clearTimeout(timer);
  });

  const dspText = $derived.by(() => {
    switch (app.status?.status) {
      case "connecting":
        return "Connecting to the DSP…";
      case "initialising":
        return "Reading the DSP configuration…";
      case "stopped":
        return "DSP connection stopped";
      default:
        return "DSP unreachable, the server is reconnecting…";
    }
  });
</script>

{#if showServer}
  <div class="banner server" role="alert">
    <span class="tag">SERVER</span>
    <span class="text">
      <strong>
        Server unreachable, reconnecting{app.retries > 1 ? ` (attempt ${app.retries})` : ""}…
      </strong>
      <span class="muted">Last known values; controls disabled.</span>
    </span>
    <button onclick={() => app.reconnectNow()}>Retry now</button>
  </div>
{:else if showDsp}
  <div class="banner dsp" role="alert" title={app.status?.error ?? undefined}>
    <span class="tag">DSP</span>
    <span class="text">
      <strong>{dspText}</strong>
      <span class="muted">Last known values; controls disabled.</span>
    </span>
  </div>
{/if}

<style>
  .banner {
    --c: var(--danger);
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px 10px;
    padding: 6px 12px;
    background: color-mix(in srgb, var(--c) 18%, var(--panel));
    border-bottom: 2px solid var(--c);
    font-size: 0.9rem;
  }
  .banner.dsp {
    --c: var(--warn);
  }
  .tag {
    padding: 1px 6px;
    border-radius: 4px;
    background: var(--c);
    color: #000;
    font-size: 0.75rem;
    font-weight: 700;
  }
  .text {
    flex: 1 1 16rem;
    min-width: 0;
  }
  .muted {
    white-space: nowrap;
  }
  button {
    min-height: 34px;
    padding: 0 10px;
  }
</style>
