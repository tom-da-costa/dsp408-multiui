<script lang="ts">
  import { app } from "../lib/app.svelte";
  import { formatDb, formatHz, formatQ, logIndexStep } from "../lib/scale";
  import type { Channel, PeqBand } from "../lib/types";
  import Field from "./Field.svelte";
  import Section from "./Section.svelte";

  interface Props {
    channel: Channel;
    path: string;
    id?: string;
    title?: string;
  }

  let { channel, path, id = "peq", title }: Props = $props();

  let expanded = $state<number | null>(null);

  const profile = $derived(app.hello?.profile);
  const limits = $derived(app.hello?.limits);
  const editable = $derived(app.editable("peq"));
  const types = $derived(profile?.peq_types ?? []);

  // Gain only matters for peak and shelf filters.
  function usesGain(type: number): boolean {
    return /peak|shelf/i.test(types[type] ?? "Peak");
  }

  function setBand(n: number, change: Partial<PeqBand>) {
    void app.set(`${path}.peq.${n}`, change);
  }
</script>

<Section {id} title={title ?? `Parametric EQ · ${channel.peq.length} bands`} kind="peq">
  {#snippet actions()}
    <button
      class="switch danger"
      class:on={channel.peq_bypass}
      disabled={!app.editable("peq_bypass")}
      aria-pressed={channel.peq_bypass}
      onclick={() => app.set(`${path}.peq_bypass`, !channel.peq_bypass)}
      title="Bypass the whole parametric EQ">Bypass</button
    >
  {/snippet}
  <ol class="bands" class:bypassed={channel.peq_bypass}>
    {#each channel.peq as band, n (n)}
      <li class:off={band.bypass} class:open={expanded === n}>
        <div class="row">
          <button
            class="summary"
            onclick={() => (expanded = expanded === n ? null : n)}
            aria-expanded={expanded === n}
          >
            <span class="n">{n + 1}</span>
            <span class="type">{types[band.type] ?? band.type}</span>
            <span class="num">{formatHz(band.freq_hz)}</span>
            <span class="num gain" class:dim={!usesGain(band.type)}>{formatDb(band.gain_db)}</span>
            <span class="num q">Q {formatQ(band.q)}</span>
          </button>
          <button
            class="switch"
            class:on={!band.bypass}
            disabled={!editable}
            aria-pressed={!band.bypass}
            aria-label={`Band ${n + 1} ${band.bypass ? "off" : "on"}`}
            onclick={() => setBand(n, { bypass: !band.bypass })}>{band.bypass ? "Off" : "On"}</button
          >
        </div>
        {#if expanded === n && profile && limits}
          <div class="editor">
            <label class="choice">
              <span>Type</span>
              <select
                value={band.type}
                disabled={!editable}
                onchange={(e) => setBand(n, { type: Number((e.currentTarget as HTMLSelectElement).value) })}
              >
                {#each types as name, i (i)}<option value={i}>{name}</option>{/each}
              </select>
            </label>
            <Field
              label="Frequency"
              value={band.freq_hz}
              min={profile.freq_min_hz}
              max={profile.freq_max_hz}
              unit="Hz"
              scale="log"
              next={(v, d) =>
                logIndexStep(v, profile.freq_min_hz, profile.freq_max_hz, profile.freq_steps ?? 300, d)}
              format={formatHz}
              disabled={!editable}
              onchange={(v) => setBand(n, { freq_hz: v })}
            />
            <Field
              label="Gain"
              value={band.gain_db}
              min={limits.eq_gain_db[0]}
              max={limits.eq_gain_db[1]}
              unit="dB"
              step={0.1}
              resolution={0.1}
              origin={0}
              format={(v) => formatDb(v)}
              disabled={!editable || !usesGain(band.type)}
              onchange={(v) => setBand(n, { gain_db: v })}
            />
            <Field
              label="Q"
              value={band.q}
              min={profile.q_min}
              max={profile.q_max}
              scale="log"
              next={(v, d) => logIndexStep(v, profile.q_min, profile.q_max, profile.q_steps ?? 100, d)}
              format={formatQ}
              disabled={!editable}
              onchange={(v) => setBand(n, { q: v })}
            />
          </div>
        {/if}
      </li>
    {/each}
  </ol>
</Section>

<style>
  .bands {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 6px;
  }
  .bands.bypassed {
    opacity: 0.55;
  }
  li {
    border: 1px solid var(--line);
    border-radius: var(--radius);
    background: var(--panel-2);
  }
  li.open {
    border-color: var(--muted);
  }
  .row {
    display: flex;
    align-items: center;
    gap: 6px;
    padding-right: 6px;
  }
  .summary {
    flex: 1;
    min-width: 0;
    display: grid;
    grid-template-columns: 20px minmax(0, 1.4fr) 1fr 1fr 1fr;
    align-items: center;
    gap: 6px;
    border: none;
    background: none;
    text-align: left;
    padding: 0 8px;
    font-size: 0.85rem;
  }
  .n {
    color: var(--muted);
    font-weight: 700;
  }
  .type {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .num {
    font-variant-numeric: tabular-nums;
    text-align: right;
  }
  .dim {
    color: var(--muted);
  }
  li.off .summary {
    color: var(--muted);
  }
  .editor {
    padding: 4px 10px 10px;
    border-top: 1px solid var(--line);
  }
  .choice {
    display: grid;
    grid-template-columns: minmax(80px, 120px) 1fr;
    align-items: center;
    gap: 6px;
    padding: 6px 0;
    color: var(--muted);
    font-size: 0.9rem;
  }
  .choice select {
    min-height: 36px;
    color: var(--text);
  }
</style>
