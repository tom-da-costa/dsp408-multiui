<script lang="ts">
  // Which inputs feed one output (its row of the routing matrix).
  import { app } from "../lib/app.svelte";
  import { slotLabel } from "../lib/nav.svelte";
  import type { OutputChannel } from "../lib/types";
  import Section from "./Section.svelte";

  interface Props {
    channel: OutputChannel;
    path: string;
    id?: string;
    title?: string;
  }

  let { channel, path, id = "routing", title = "Routing" }: Props = $props();

  const inputs = $derived(app.device?.inputs ?? []);

  function toggle(inputIndex: number) {
    const matrix = channel.matrix.map((on, i) => (i === inputIndex ? !on : on));
    void app.set(`${path}.matrix`, matrix);
  }
</script>

<Section {id} {title} kind="matrix">
  <div class="row" role="group" aria-label="Inputs routed to this output">
    {#each channel.matrix as on, i (i)}
      <button
        class="ch-bar"
        style:--ch={app.color(`inputs.${i}`)}
        class:on
        aria-pressed={on}
        disabled={!app.editable("matrix")}
        title={`${slotLabel(`inputs.${i}`)} ${inputs[i]?.name ?? ""}`}
        onclick={() => toggle(i)}
      >
        <span>{slotLabel(`inputs.${i}`).replace("In ", "")}</span>
        <small>{inputs[i]?.name || "—"}</small>
      </button>
    {/each}
  </div>
</Section>

<style>
  .row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(52px, 1fr));
    gap: 6px;
  }
  button {
    display: grid;
    padding: 4px 2px;
    line-height: 1.1;
    min-width: 0;
  }
  span {
    font-weight: 700;
  }
  small {
    font-size: 0.7rem;
    color: var(--muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  button:not(.on) {
    background: color-mix(in srgb, var(--ch) 16%, var(--panel-2));
    border-color: color-mix(in srgb, var(--ch) 60%, var(--line));
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
