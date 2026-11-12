<script lang="ts">
  import { app } from "../lib/app.svelte";
  import { links } from "../lib/links.svelte";
  import {
    METER_MAX_RANGE,
    METER_MIN_RANGE,
    METER_RANGE_STEP,
    METER_SEGMENTS,
    meterRange,
  } from "../lib/meterrange.svelte";
  import { SIGNAL_DEFAULT_DB, SIGNAL_RANGE_DB, signal } from "../lib/signal.svelte";
  import Stepper from "./Stepper.svelte";

  let rate = $state(app.settings?.meter_rate_hz ?? 5);

  $effect(() => {
    if (app.settings) rate = app.settings.meter_rate_hz;
  });

  const RATE_RANGE = [1, 10] as const;
  const rateLocked = $derived(app.lockedByOther || app.screenLocked);

  async function saveRate(hz: number) {
    rate = hz;
    await app.run({ type: "settings.set", meter_rate_hz: hz });
  }

  // Whole dB, with a sign above 0 (formatDb would show −∞ at the gain floor, −60).
  const dbu = (db: number) => `${db > 0 ? "+" : ""}${db} dBu`;

  const otherMaster = $derived(!!app.master?.owner_id && !app.iAmMaster);

  async function toggleMaster() {
    await app.run({ type: app.iAmMaster ? "master.release" : "master.acquire" });
  }

  async function blockLogins(blocked: boolean) {
    await app.run({ type: "logins.block", blocked });
  }

  async function kick(id: string, name: string) {
    if (!confirm(`Disconnect ${name}? They go back to the login screen.`)) return;
    if (await app.run({ type: "client.kick", client_id: id })) app.toast(`${name} disconnected`);
  }

  // Same rule as the server: refused while another client has Control or is the master.
  const canShutdown = $derived(
    app.connected && !app.screenLocked && !app.lockedByOther && !otherMaster,
  );

  async function shutdown() {
    const question =
      "Disconnect from the DSP and shut the server down?\n\n" +
      "Every connected client loses the app until the server is started again. " +
      "The DSP keeps its current settings.";
    if (!confirm(question)) return;
    await app.run({ type: "server.shutdown" });
  }

  async function refresh() {
    if (await app.run({ type: "resync" })) app.toast("Configuration re-read from the DSP");
  }
</script>

<div class="grid">
  <section class="card">
    <h2>Meters</h2>
    <Stepper
      id="meter-rate"
      label="Refresh rate"
      value={rate}
      min={RATE_RANGE[0]}
      max={RATE_RANGE[1]}
      format={(hz) => `${hz} Hz`}
      disabled={rateLocked}
      onchange={saveRate}
    />
    <p class="muted">Applies to every connected client.</p>
    <Stepper
      id="meter-min"
      label="Scale bottom"
      value={meterRange.min}
      min={METER_MIN_RANGE[0]}
      max={METER_MIN_RANGE[1]}
      step={METER_RANGE_STEP}
      format={dbu}
      disabled={app.screenLocked}
      live
      onchange={(db) => meterRange.setMin(db)}
    />
    <Stepper
      id="meter-max"
      label="Scale top"
      value={meterRange.max}
      min={METER_MAX_RANGE[0]}
      max={METER_MAX_RANGE[1]}
      step={METER_RANGE_STEP}
      format={dbu}
      disabled={app.screenLocked}
      live
      onchange={(db) => meterRange.setMax(db)}
    />
    <div class="setting-row">
      <label for="meter-segments">Segments:</label>
      <select
        id="meter-segments"
        value={meterRange.segment}
        disabled={app.screenLocked}
        onchange={(e) => meterRange.setSegment(Number(e.currentTarget.value))}
      >
        {#each METER_SEGMENTS as step (step)}
          <option value={step}>{step ? `${step} dB` : "Continuous"}</option>
        {/each}
      </select>
    </div>
    <p class="muted">
      The range every meter shows (−40 to +20 dBu by default; the DSP's full scale is +20 dBu),
      as a continuous bar or as segments (LED style; a segment takes the colour of its top).
      Levels, CLIP and the colour zones do not change. This browser only.
      {#if !meterRange.isDefault}
        <button class="link" disabled={app.screenLocked} onclick={() => meterRange.reset()}
          >Reset</button
        >
      {/if}
    </p>
  </section>

  <section class="card">
    <h2>Display</h2>
    <label class="check">
      <input
        type="checkbox"
        checked={links.merge}
        disabled={app.screenLocked}
        onchange={(e) => links.setMerge(e.currentTarget.checked)}
      />
      Merge linked channels
    </label>
    <p class="muted">
      Linked channels show as one (e.g. "Out 1+5") in every view except the Matrix and Link
      tabs: a change applies to all of them, as the DSP does. Names and routing stay per channel;
      meters show the loudest. This browser only.
    </p>
    <Stepper
      id="signal-threshold"
      label="Signal indicator (SIG) above"
      value={signal.threshold}
      min={SIGNAL_RANGE_DB[0]}
      max={SIGNAL_RANGE_DB[1]}
      format={dbu}
      disabled={app.screenLocked}
      live
      onchange={(db) => signal.setThreshold(db)}
    />
    <p class="muted">
      SIG lights while a channel's level is above this ({SIGNAL_DEFAULT_DB} dBu by default; an
      unconnected input reads about −86 dBu). This browser only.
    </p>
  </section>

  <section class="card">
    <h2>Connected clients ({app.clients.length})</h2>
    <ul class="clients">
      {#each app.clients as client (client.id)}
        <li>
          <span class="who">
            {client.name}
            {#if client.id === app.hello?.client_id}<span class="muted">(you)</span>{/if}
            {#if client.id === app.master?.owner_id}<span class="badge master">master</span>{/if}
            {#if client.id === app.lock?.owner_id}<span class="badge">control</span>{/if}
          </span>
          {#if app.iAmMaster && client.id !== app.hello?.client_id}
            <button
              class="danger small"
              onclick={() => kick(client.id, client.name)}
              disabled={app.screenLocked}>Disconnect</button
            >
          {/if}
        </li>
      {/each}
    </ul>
    <h3>Master</h3>
    <p class="muted">
      {#if app.iAmMaster}
        You are the master: you can disconnect the other clients and block new connections.
      {:else if otherMaster}
        {app.master?.owner_name} is the master{app.master?.logins_blocked
          ? " and has blocked new connections"
          : ""}.
      {:else}
        Nobody is the master. The master can disconnect the other clients and block new
        connections.
      {/if}
    </p>
    {#if app.iAmMaster}
      <label class="check">
        <input
          type="checkbox"
          checked={app.master?.logins_blocked ?? false}
          disabled={app.screenLocked}
          onchange={(e) => blockLogins(e.currentTarget.checked)}
        />
        Block new connections
      </label>
      <p class="muted">
        Browsers already connected stay connected (a reload or a Wi-Fi drop is fine). The
        block ends with your master role, also when you have had the app closed for 5 minutes.
      </p>
    {/if}
    <div class="actions">
      <button onclick={toggleMaster} disabled={otherMaster || app.screenLocked || !app.connected}>
        {app.iAmMaster ? "Stop being master" : "Become master"}
      </button>
    </div>
  </section>

  <section class="card">
    <h2>Device</h2>
    <dl>
      <dt>Status</dt>
      <dd>{app.status?.status ?? "—"}{app.status?.error ? ` (${app.status.error})` : ""}</dd>
      <dt>Model</dt>
      <dd>
        {app.status?.model || "—"}
        {#if app.status?.model && app.status.model_tested === false}
          <span class="muted">(not tested by this project yet: reports welcome)</span>
        {/if}
      </dd>
      <dt>Firmware</dt>
      <dd>{app.status?.firmware || "—"}</dd>
      <dt>Server</dt>
      <dd>{app.hello?.server_version ?? "—"}{app.hello?.demo ? " (demo mode)" : ""}</dd>
    </dl>
    <div class="actions">
      <button onclick={refresh} disabled={app.readOnly}>Refresh from device</button>
      <button class="danger" onclick={shutdown} disabled={!canShutdown}>
        Disconnect from DSP and shutdown
      </button>
    </div>
    <p class="muted">
      Shut the server down cleanly: it frees the DSP (which accepts one program at a time) and
      stops the app for every client.
      {#if app.lockedByOther}Only {app.lock?.owner_name}, who has control, can do it now.
      {:else if otherMaster}Only {app.master?.owner_name}, the master, can do it now.{/if}
    </p>
  </section>

  <section class="card">
    <h2>This browser</h2>
    <p>Connected as <strong>{app.hello?.name ?? app.me?.name ?? "—"}</strong>.</p>
    <div class="actions">
      <button class="danger" onclick={() => app.logout()}>Log out</button>
    </div>
    <p class="muted">Leaves the app on this browser only; the server and the DSP keep running.</p>
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
  label.check {
    display: flex;
    align-items: center;
    gap: 10px;
    min-height: var(--tap);
  }
  label.check input {
    width: 22px;
    height: 22px;
    margin: 0;
  }
  .setting-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    margin: 12px 0 8px;
  }
  .setting-row select {
    flex: 1;
    min-height: var(--tap);
  }
  .link {
    min-height: 0;
    padding: 0 4px;
    border: none;
    background: none;
    color: var(--accent);
    text-decoration: underline;
  }
  ul {
    margin: 0;
    padding-left: 18px;
  }
  .clients {
    list-style: none;
    padding: 0;
    display: grid;
    gap: 4px;
  }
  .clients li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    min-height: 36px;
  }
  .who {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  button.small {
    min-height: 32px;
    padding: 0 10px;
    font-size: 0.85rem;
  }
  h3 {
    margin: 12px 0 4px;
    font-size: 1rem;
  }
  .badge.master {
    background: var(--info);
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
