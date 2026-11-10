<script lang="ts">
  // Bottom of the tab rail: who I am (tap: Settings) and the lock button.
  import { app } from "../lib/app.svelte";
  import { nav } from "../lib/nav.svelte";

  interface Props {
    expanded: boolean;
    onpick?: () => void; // called after a tap that navigates (folds the rail on a phone)
  }

  let { expanded, onpick }: Props = $props();

  let now = $state(performance.now());
  $effect(() => {
    const timer = setInterval(() => (now = performance.now()), 1000);
    return () => clearInterval(timer);
  });

  const remaining = $derived(
    app.lockDeadline === null ? null : Math.max(0, Math.round((app.lockDeadline - now) / 1000)),
  );
  const me = $derived(app.me?.name ?? "");

  function mmss(seconds: number): string {
    return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  }

  async function toggleLock() {
    if (app.iOwnLock) await app.run({ type: "lock.release" });
    else await app.run({ type: "lock.acquire" });
  }

  function openSettings() {
    nav.select("settings");
    onpick?.();
  }
</script>

<div class="block" class:expanded>
  <button class="me" onclick={openSettings} title={`You are "${me}"`}>
    <span class="icon" aria-hidden="true">👤</span>
    <span class="name">{me}</span>
  </button>

  {#if app.lockedByOther}
    <div class="lock other" title={`Read-only: locked by ${app.lock?.owner_name ?? "someone"}`}>
      <span class="icon">🔒</span>
      <span class="text">{app.lock?.owner_name}</span>
    </div>
  {:else}
    <button
      class="lock"
      class:mine={app.iOwnLock}
      onclick={toggleLock}
      disabled={!app.connected}
      title={app.iOwnLock ? "Release the lock" : "Lock the controls for me"}
    >
      <span class="icon">
        {app.iOwnLock ? "🔓" : "🔒"}
        {#if app.iOwnLock && remaining !== null && !expanded}<small>{mmss(remaining)}</small>{/if}
      </span>
      <span class="text"
        >{#if app.iOwnLock}Unlock {remaining !== null ? mmss(remaining) : ""}{:else}Lock{/if}</span
      >
    </button>
  {/if}
</div>

<style>
  .block {
    display: grid;
    gap: 2px;
    margin-top: auto; /* bottom of the rail */
    padding-top: 6px;
    border-top: 1px solid var(--line);
  }
  button,
  .other {
    display: flex;
    align-items: center;
    gap: 12px;
    min-height: 52px;
    margin: 0 6px;
    padding: 0 6px;
    border: none;
    border-radius: 8px;
    background: none;
    text-align: left;
    white-space: nowrap;
    min-width: 0;
  }
  .me {
    min-height: 36px;
    color: var(--muted);
    font-size: 0.85rem;
  }
  .icon {
    flex: 0 0 32px;
    display: grid;
    justify-items: center;
    gap: 2px;
    font-size: 1.15rem;
    line-height: 1;
  }
  .me .icon {
    font-size: 0.95rem;
  }
  .icon small {
    font-size: 0.6rem;
    font-variant-numeric: tabular-nums;
  }
  .name,
  .text {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  /* Folded: the name is shown small under the icon instead of beside it. */
  .block:not(.expanded) .me {
    flex-direction: column;
    justify-content: center;
    gap: 2px;
    padding: 4px 0;
  }
  .block:not(.expanded) .name {
    max-width: 44px;
    font-size: 0.6rem;
    text-align: center;
  }
  .text {
    opacity: 0;
    transition: opacity 0.1s;
  }
  .expanded .text {
    opacity: 1;
  }
  .lock.mine {
    background: var(--warn);
    color: #000;
  }
  .other {
    color: var(--warn);
  }
</style>
