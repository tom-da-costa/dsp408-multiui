<script lang="ts">
  // A horizontally scrolling row of chips: sub-tabs (one selected) or toggles (several on).
  interface Item {
    key: string;
    label: string;
    sub?: string; // second line (a channel name)
    color?: string; // channel colour (lib/colors.ts), shown as a bar under the chip
    disabled?: boolean;
  }

  interface Props {
    items: Item[];
    /** Selected key (tabs) or keys (toggles). */
    selected: string | string[];
    onselect: (key: string) => void;
    label: string; // accessible name of the group
  }

  let { items, selected, onselect, label }: Props = $props();

  const toggles = $derived(Array.isArray(selected));
  let bar = $state<HTMLDivElement>();

  function isOn(key: string): boolean {
    return Array.isArray(selected) ? selected.includes(key) : selected === key;
  }

  // Keep the selected tab visible (on a phone the row is wider than the screen).
  $effect(() => {
    if (toggles || !bar) return;
    const key = selected as string;
    bar.querySelector<HTMLElement>(`[data-key="${CSS.escape(key)}"]`)?.scrollIntoView({
      block: "nearest",
      inline: "nearest",
    });
  });
</script>

<div class="chips" bind:this={bar} role={toggles ? "group" : "tablist"} aria-label={label}>
  {#each items as item (item.key)}
    <button
      data-key={item.key}
      class:on={isOn(item.key)}
      class:two={item.sub !== undefined}
      class:ch-bar={item.color !== undefined}
      style:--ch={item.color}
      role={toggles ? undefined : "tab"}
      aria-selected={toggles ? undefined : isOn(item.key)}
      aria-pressed={toggles ? isOn(item.key) : undefined}
      disabled={item.disabled}
      onclick={() => onselect(item.key)}
    >
      <span>{item.label}</span>
      {#if item.sub !== undefined}<small>{item.sub || "—"}</small>{/if}
    </button>
  {/each}
</div>

<style>
  .chips {
    display: flex;
    gap: 6px;
    overflow-x: auto;
    overscroll-behavior-x: contain;
    scrollbar-width: none;
    padding: 0 0 10px;
  }
  .chips::-webkit-scrollbar {
    display: none;
  }
  button {
    flex: 0 0 auto;
    min-height: 36px;
    border-radius: 18px;
    display: grid;
    align-content: center;
    line-height: 1.1;
    white-space: nowrap;
  }
  button.two {
    min-height: 44px;
    border-radius: 12px;
    padding: 0 12px;
  }
  small {
    font-size: 0.7rem;
    color: var(--muted);
    max-width: 9ch;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .on {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--accent-text);
  }
  .on small {
    color: inherit;
    opacity: 0.75;
  }
</style>
