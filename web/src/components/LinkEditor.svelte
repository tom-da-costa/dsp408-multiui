<script lang="ts">
  // Channel links: tap channels to select them, then link or unlink them. Linking copies the
  // settings of the first selected channel onto the others (the DSP does it), except names and
  // routing; afterwards every change on one member applies to the whole group.
  import { app } from "../lib/app.svelte";
  import { slotLabel } from "../lib/nav.svelte";
  import type { Channel } from "../lib/types";

  type Side = "inputs" | "outputs";

  let selected = $state<Record<Side, number[]>>({ inputs: [], outputs: [] });
  let confirming = $state<Side | null>(null);
  let busy = $state(false);

  const device = $derived(app.device);
  const editable = $derived(app.editable("link"));

  function channels(side: Side): Channel[] {
    return (side === "inputs" ? device?.inputs : device?.outputs) ?? [];
  }

  /** Current groups of a side (indices), each sorted, the master first. */
  function groups(side: Side): number[][] {
    const seen = new Set<string>();
    const result: number[][] = [];
    channels(side).forEach((ch, i) => {
      if (!ch.linked.length) return;
      const group = [i, ...ch.linked].sort((a, b) => a - b);
      const key = group.join(",");
      if (!seen.has(key)) {
        seen.add(key);
        result.push(group);
      }
    });
    return result;
  }

  function groupOf(side: Side, i: number): number {
    return groups(side).findIndex((g) => g.includes(i));
  }

  function label(side: Side, i: number): string {
    return slotLabel(`${side}.${i}`);
  }

  function toggle(side: Side, i: number) {
    confirming = null;
    const list = selected[side];
    selected[side] = list.includes(i) ? list.filter((n) => n !== i) : [...list, i].sort((a, b) => a - b);
  }

  async function apply(side: Side, next: number[][]) {
    busy = true;
    const ok = await app.run({ type: "link.set", side, groups: next });
    busy = false;
    confirming = null;
    if (ok) selected[side] = [];
  }

  function link(side: Side) {
    const chosen = selected[side];
    const rest = groups(side)
      .map((g) => g.filter((i) => !chosen.includes(i)))
      .filter((g) => g.length > 1);
    void apply(side, [...rest, chosen]);
  }

  function unlink(side: Side) {
    const chosen = selected[side];
    const rest = groups(side)
      .map((g) => g.filter((i) => !chosen.includes(i)))
      .filter((g) => g.length > 1);
    void apply(side, rest);
  }
</script>

{#if device}
  <div class="sides">
    {#each ["inputs", "outputs"] as const as side (side)}
      {@const chosen = selected[side]}
      {@const linkedChosen = chosen.some((i) => groupOf(side, i) >= 0)}
      <section class="card">
        <h2>{side === "inputs" ? "Inputs" : "Outputs"}</h2>
        <div class="chips" role="group" aria-label={`${side} to link`}>
          {#each channels(side) as ch, i (i)}
            {@const g = groupOf(side, i)}
            <button
              class="ch-bar"
              style:--ch={app.color(`${side}.${i}`)}
              class:on={chosen.includes(i)}
              aria-pressed={chosen.includes(i)}
              disabled={!editable || busy}
              onclick={() => toggle(side, i)}
            >
              <span class="slot">{label(side, i)}</span>
              <small>{ch.name || "—"}</small>
              {#if g >= 0}
                <span class="badge" style:background={app.color(`${side}.${i}`)}
                  >🔗 {g + 1}</span
                >
              {/if}
            </button>
          {/each}
        </div>

        <ul class="groups">
          {#each groups(side) as group, g (group.join())}
            <li>
              <span class="dot" style:background={app.color(`${side}.${group[0]}`)}></span>
              Group {g + 1}: {group.map((i) => label(side, i)).join(" + ")}
            </li>
          {:else}
            <li class="muted">No linked channels.</li>
          {/each}
        </ul>

        {#if confirming === side}
          <div class="confirm">
            <p>
              {chosen.slice(1).map((i) => label(side, i)).join(", ")}
              {chosen.length > 2 ? "take" : "takes"} every setting of
              <strong>{label(side, chosen[0] ?? 0)}</strong> (gain, delay, EQ, filters, dynamics…),
              except the name and the routing. Then any change applies to the whole group.
            </p>
            <div class="actions">
              <button class="primary" disabled={busy} onclick={() => link(side)}>Link</button>
              <button disabled={busy} onclick={() => (confirming = null)}>Cancel</button>
            </div>
          </div>
        {:else}
          <div class="actions">
            <button
              class="primary"
              disabled={!editable || busy || chosen.length < 2}
              onclick={() => (confirming = side)}>Link selected</button
            >
            <button disabled={!editable || busy || !linkedChosen} onclick={() => unlink(side)}
              >Unlink selected</button
            >
            {#if chosen.length}
              <button disabled={busy} onclick={() => (selected[side] = [])}>Clear</button>
            {/if}
          </div>
        {/if}
      </section>
    {/each}
  </div>
  <p class="muted hint">
    Tap channels to select them. The first selected channel (lowest number) is the master. Linked
    channels keep their own name and routing.
  </p>
{/if}

<style>
  .sides {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 10px;
  }
  .chips {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
  }
  .chips button {
    position: relative;
    display: grid;
    padding: 6px 4px;
    line-height: 1.15;
    min-width: 0;
  }
  .slot {
    font-weight: 700;
  }
  small {
    font-size: 0.7rem;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .on {
    outline: 2px solid var(--accent);
    outline-offset: -2px;
    background: color-mix(in srgb, var(--accent) 18%, var(--panel-2));
  }
  .badge {
    justify-self: center;
    margin-top: 3px;
    padding: 0 5px;
    border-radius: 8px;
    font-size: 0.65rem;
    font-weight: 700;
    color: #000;
  }
  .groups {
    list-style: none;
    margin: 12px 0;
    padding: 0;
    display: grid;
    gap: 4px;
    font-size: 0.9rem;
  }
  .dot {
    display: inline-block;
    width: 10px;
    height: 10px;
    border-radius: 50%;
    margin-right: 6px;
  }
  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .confirm {
    padding: 10px;
    border-radius: 8px;
    background: var(--panel-2);
    border: 1px solid var(--warn);
  }
  .confirm p {
    margin: 0 0 10px;
    font-size: 0.9rem;
  }
  .hint {
    font-size: 0.85rem;
  }
</style>
