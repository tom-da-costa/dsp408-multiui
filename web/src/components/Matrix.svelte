<script lang="ts">
  import { app } from "../lib/app.svelte";

  const device = $derived(app.device);

  function toggle(outputIndex: number, inputIndex: number) {
    const output = device?.outputs[outputIndex];
    if (!output) return;
    const matrix = output.matrix.map((on, i) => (i === inputIndex ? !on : on));
    void app.set(`outputs.${outputIndex}.matrix`, matrix);
  }
</script>

{#if device}
  <div class="card">
    <h2>Routing matrix</h2>
    <table>
      <thead>
        <tr>
          <th></th>
          {#each device.inputs as input, i (input.index)}<th style:color={app.color(`inputs.${i}`)}
              >{input.name}</th
            >{/each}
        </tr>
      </thead>
      <tbody>
        {#each device.outputs as output, o (output.index)}
          <tr>
            <th scope="row" style:color={app.color(`outputs.${o}`)}>{output.name}</th>
            {#each output.matrix as on, i (i)}
              <td>
                <button
                  class:on
                  aria-pressed={on}
                  aria-label={`${device.inputs[i]?.name} to ${output.name}`}
                  disabled={app.readOnly}
                  onclick={() => toggle(o, i)}>{on ? "●" : ""}</button
                >
              </td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  table {
    border-collapse: separate;
    border-spacing: 6px;
    margin: -6px;
  }
  th {
    font-size: 0.8rem;
    font-weight: 600;
    color: var(--muted);
    text-align: center;
    white-space: nowrap;
  }
  th[scope="row"] {
    text-align: right;
    padding-right: 4px;
    color: var(--text);
  }
  td button {
    width: var(--tap);
    padding: 0;
    font-size: 1.1rem;
  }
  td button.on {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--accent-text);
  }
</style>
