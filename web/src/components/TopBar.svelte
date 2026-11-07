<script lang="ts">
  import { app } from "../lib/app.svelte";

  let now = $state(performance.now());

  $effect(() => {
    const timer = setInterval(() => (now = performance.now()), 1000);
    return () => clearInterval(timer);
  });

  const remaining = $derived(
    app.lockDeadline === null ? null : Math.max(0, Math.round((app.lockDeadline - now) / 1000)),
  );
  const status = $derived(app.connected ? (app.status?.status ?? "connecting") : "disconnected");

  function mmss(seconds: number): string {
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  }

  async function toggleLock() {
    if (app.iOwnLock) await app.run({ type: "lock.release" });
    else await app.run({ type: "lock.acquire" });
  }
</script>

<header>
  <span class="dot {status}" title={app.status?.error ?? status}></span>
  <div class="title">
    <strong>{app.device?.preset_name || "DSP 408"}</strong>
    <span class="muted">{status === "online" ? (app.status?.model ?? "") : status}</span>
  </div>
  {#if app.hello?.simulator}<span class="sim">SIMULATOR</span>{/if}
  {#if app.lockedByOther}
    <span class="lock other" title="Controls are read-only">🔒 {app.lock?.owner_name}</span>
  {:else}
    <button class="lock" class:mine={app.iOwnLock} onclick={toggleLock} disabled={!app.connected}>
      {#if app.iOwnLock}🔓 Unlock {remaining !== null ? mmss(remaining) : ""}{:else}🔒 Lock{/if}
    </button>
  {/if}
</header>

<style>
  header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 12px;
    padding-top: max(8px, env(safe-area-inset-top));
    background: var(--panel);
    border-bottom: 1px solid var(--line);
  }
  .dot {
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: var(--muted);
    flex: none;
  }
  .dot.online {
    background: var(--accent);
  }
  .dot.offline,
  .dot.disconnected {
    background: var(--danger);
  }
  .dot.connecting,
  .dot.initialising {
    background: var(--warn);
  }
  .title {
    display: grid;
    min-width: 0;
    flex: 1;
  }
  .title strong,
  .title span {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .title span {
    font-size: 0.8rem;
  }
  .sim {
    font-size: 0.7rem;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 6px;
    background: var(--info);
    color: #000;
  }
  .lock {
    white-space: nowrap;
  }
  .lock.mine {
    background: var(--warn);
    border-color: var(--warn);
    color: #000;
    font-variant-numeric: tabular-nums;
  }
  .lock.other {
    padding: 6px 10px;
    border-radius: var(--radius);
    background: var(--panel-2);
    color: var(--warn);
    font-size: 0.9rem;
  }
</style>
