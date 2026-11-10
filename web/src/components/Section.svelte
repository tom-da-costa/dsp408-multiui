<script lang="ts">
  // A collapsible card of the channel detail, with the "not hardware-verified" badge. In a
  // strip (lib/layout.ts) only the badge, the actions and the content are shown.
  import type { Snippet } from "svelte";
  import { app } from "../lib/app.svelte";
  import { inStrip } from "../lib/layout";
  import { nav } from "../lib/nav.svelte";

  interface Props {
    id: string;
    title: string;
    /** Parameter kind (registry name) used for the verification badge. */
    kind?: string;
    actions?: Snippet;
    children: Snippet;
  }

  let { id, title, kind, actions, children }: Props = $props();

  const bare = inStrip();
  const open = $derived(nav.isOpen(id));
  const unverified = $derived(kind !== undefined && !app.verified(kind));
  const blocked = $derived(unverified && !app.hello?.experimental);
</script>

{#snippet badge()}
  {#if unverified}
    <span
      class="badge"
      class:blocked
      title={blocked
        ? "Not verified on a real DSP 408 yet: start the server with --experimental to edit it"
        : "Not verified on a real DSP 408 yet"}>{blocked ? "locked: experimental" : "unverified"}</span
    >
  {/if}
{/snippet}

{#if bare}
  <div class="bare">
    {#if unverified || actions}
      <div class="bare-head">{@render badge()}{#if actions}{@render actions()}{/if}</div>
    {/if}
    {@render children()}
  </div>
{:else}
<section class="card">
  <header>
    <button class="title" onclick={() => nav.toggle(id)} aria-expanded={open}>
      <span class="chevron" class:open aria-hidden="true">›</span>{title}
    </button>
    {@render badge()}
    {#if actions && open}<div class="actions">{@render actions()}</div>{/if}
  </header>
  {#if open}<div class="body">{@render children()}</div>{/if}
</section>
{/if}

<style>
  section {
    padding: 4px 12px;
    break-inside: avoid;
    margin-bottom: 10px;
  }
  header {
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: 48px;
  }
  .title {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 8px;
    border: none;
    background: none;
    padding: 0;
    font-weight: 600;
    font-size: 1rem;
    text-align: left;
  }
  .chevron {
    display: inline-block;
    width: 12px;
    color: var(--muted);
    transition: transform 0.15s;
  }
  .chevron.open {
    transform: rotate(90deg);
  }
  .badge {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 2px 6px;
    border-radius: 4px;
    border: 1px solid var(--warn);
    color: var(--warn);
    white-space: nowrap;
  }
  .badge.blocked {
    border-color: var(--danger);
    color: var(--danger);
  }
  .actions {
    display: flex;
    gap: 6px;
  }
  .body {
    padding-bottom: 10px;
  }
  .bare {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .bare-head {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 6px;
  }
</style>
