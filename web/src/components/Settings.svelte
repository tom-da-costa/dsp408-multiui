<script lang="ts">
  import { app } from "../lib/app.svelte";

  let rate = $state(app.settings?.meter_rate_hz ?? 5);
  let name = $state(app.me?.name ?? "");

  $effect(() => {
    if (app.settings) rate = app.settings.meter_rate_hz;
  });

  async function saveRate() {
    await app.run({ type: "settings.set", meter_rate_hz: rate });
  }

  async function rename(event: SubmitEvent) {
    event.preventDefault();
    if (await app.run({ type: "rename", name })) app.toast("Name updated");
  }

  async function refresh() {
    if (await app.run({ type: "resync" })) app.toast("Configuration re-read from the DSP");
  }
</script>

<div class="grid">
  <section class="card">
    <h2>Meters</h2>
    <label>
      Refresh rate: <strong>{rate} Hz</strong>
      <input
        type="range"
        min="1"
        max="10"
        step="1"
        bind:value={rate}
        onchange={saveRate}
        disabled={app.lockedByOther}
      />
    </label>
    <p class="muted">Applies to every connected client.</p>
  </section>

  <section class="card">
    <h2>You</h2>
    <form onsubmit={rename}>
      <input type="text" maxlength="32" bind:value={name} aria-label="Display name" />
      <button type="submit">Rename</button>
    </form>
  </section>

  <section class="card">
    <h2>Connected clients ({app.clients.length})</h2>
    <ul>
      {#each app.clients as client (client.id)}
        <li>
          {client.name}
          {#if client.id === app.hello?.client_id}<span class="muted">(you)</span>{/if}
          {#if client.id === app.lock?.owner_id}<span class="badge">lock</span>{/if}
        </li>
      {/each}
    </ul>
  </section>

  <section class="card">
    <h2>Device</h2>
    <dl>
      <dt>Status</dt>
      <dd>{app.status?.status ?? "—"}{app.status?.error ? ` (${app.status.error})` : ""}</dd>
      <dt>Model</dt>
      <dd>{app.status?.model || "—"}</dd>
      <dt>Firmware</dt>
      <dd>{app.status?.firmware || "—"}</dd>
      <dt>Server</dt>
      <dd>{app.hello?.server_version ?? "—"}{app.hello?.simulator ? " (simulator)" : ""}</dd>
    </dl>
    <div class="actions">
      <button onclick={refresh} disabled={app.readOnly}>Refresh from device</button>
      <button class="danger" onclick={() => app.logout()}>Log out</button>
    </div>
  </section>
</div>

<style>
  .grid {
    display: grid;
    gap: 12px;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  }
  label {
    display: grid;
    gap: 8px;
  }
  input[type="range"] {
    width: 100%;
    min-height: var(--tap);
  }
  form {
    display: flex;
    gap: 8px;
  }
  ul {
    margin: 0;
    padding-left: 18px;
  }
  .badge {
    font-size: 0.7rem;
    padding: 1px 6px;
    border-radius: 8px;
    background: var(--warn);
    color: #000;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 4px 12px;
    margin: 0 0 12px;
  }
  dt {
    color: var(--muted);
  }
  dd {
    margin: 0;
  }
  .actions {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
  }
</style>
