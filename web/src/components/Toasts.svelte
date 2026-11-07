<script lang="ts">
  import { app } from "../lib/app.svelte";
</script>

<div class="toasts" aria-live="polite">
  {#each app.toasts as toast (toast.id)}
    <div class="toast {toast.kind}">{toast.text}</div>
  {/each}
</div>

<style>
  .toasts {
    position: fixed;
    left: 50%;
    bottom: calc(76px + env(safe-area-inset-bottom));
    transform: translateX(-50%);
    display: grid;
    gap: 6px;
    z-index: 20;
    width: min(420px, calc(100% - 32px));
    pointer-events: none;
  }
  .toast {
    padding: 10px 14px;
    border-radius: var(--radius);
    background: var(--panel-2);
    border: 1px solid var(--line);
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.4);
  }
  .toast.error {
    border-color: var(--danger);
  }
</style>
