<script lang="ts">
  // "All-in-one" tab: one column per channel with the settings picked in the chip row, for the
  // channels picked in the row below (as in the Live tab). Both are remembered in this browser.
  import { app } from "../lib/app.svelte";
  import { nav, PARAM_SCOPE, PARAMS, slotLabel, type Param } from "../lib/nav.svelte";
  import { ChannelSelection } from "../lib/selection.svelte";
  import ChannelPicker from "./ChannelPicker.svelte";
  import ChipBar from "./ChipBar.svelte";
  import LevelBar from "./LevelBar.svelte";
  import NameEditor from "./NameEditor.svelte";
  import ParamBlock from "./ParamBlock.svelte";

  const STORAGE_KEY = "dsp408.aio.params";
  const DEFAULT: Param[] = ["gain", "delay", "filters", "comp", "limit", "gate", "matrix"];

  function load(): Param[] {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null") as unknown;
      if (Array.isArray(saved)) return PARAMS.map(([k]) => k).filter((k) => saved.includes(k));
    } catch {
      // storage unavailable or corrupt: use the default
    }
    return DEFAULT;
  }

  let shown = $state<Param[]>(load());

  function toggle(key: string) {
    const param = key as Param;
    // Keep the PARAMS order whatever the click order.
    shown = PARAMS.map(([k]) => k).filter((k) => (k === param ? !shown.includes(k) : shown.includes(k)));
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(shown));
    } catch {
      // not persisted: fine
    }
  }

  const selection = new ChannelSelection("dsp408.aio.hidden");
  const device = $derived(app.device);
  const channels = $derived(
    selection.shown.flatMap((path) => {
      const [side, n] = path.split(".");
      const channel = (side === "inputs" ? device?.inputs : device?.outputs)?.[Number(n)];
      return channel ? [{ path, channel }] : [];
    }),
  );

  /** Channel whose name is being edited in its column header. */
  let renaming = $state<string | null>(null);

  function applies(param: Param, path: string): boolean {
    const scope = PARAM_SCOPE[param];
    return scope === "all" || path.startsWith(scope);
  }
</script>

<ChipBar
  items={PARAMS.filter(([key]) => key !== "link").map(([key, label]) => ({ key, label }))}
  selected={shown}
  onselect={toggle}
  label="Settings shown"
/>
<ChannelPicker {selection} />

<div class="strips">
  {#each channels as { path, channel }, i (path)}
    {#if i > 0 && path.startsWith("outputs.") && channels[i - 1]?.path.startsWith("inputs.")}
      <div class="divider"></div>
    {/if}
    <section class="strip" class:muted={channel.mute} style:--ch={app.color(path)}>
      {#if renaming === path}
        <NameEditor {channel} {path} compact autofocus ondone={() => (renaming = null)} />
      {:else}
        <div class="head">
          <button class="open" onclick={() => nav.open(path)} title="Open this channel">
            <span class="slot">{slotLabel(path)}{channel.linked.length ? " 🔗" : ""}</span>
            <strong>{channel.name || "—"}</strong>
          </button>
          <button
            class="edit"
            disabled={!app.editable("name")}
            onclick={() => (renaming = path)}
            title="Rename this channel"
            aria-label={`Rename ${slotLabel(path)}`}>✎</button
          >
        </div>
      {/if}
      <LevelBar {path} compact />
      {#each shown.filter((p) => applies(p, path)) as param (param)}
        <ParamBlock {param} {path} />
      {/each}
    </section>
  {:else}
    <p class="muted">No channel selected: pick some above.</p>
  {/each}
  {#if shown.length === 0 && channels.length > 0}
    <p class="muted">Pick the settings to show above.</p>
  {/if}
</div>

<style>
  .strips {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    overflow-x: auto;
    overscroll-behavior-x: contain;
    scroll-snap-type: x proximity;
    padding-bottom: 8px;
  }
  .divider {
    flex: 0 0 2px;
    align-self: stretch;
    background: var(--line);
    border-radius: 1px;
  }
  .strip {
    flex: 0 0 min(300px, calc(100vw - 110px));
    scroll-snap-align: start;
    display: grid;
    gap: 8px;
    padding: 8px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius);
  }
  .strip :global(section.card) {
    margin: 0;
    background: var(--panel-2);
  }
  .head {
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 4px;
  }
  .head button {
    border: 2px solid var(--ch);
    color: var(--ch);
    min-height: 40px;
    background: none;
  }
  .open {
    display: grid;
    justify-items: start;
    min-width: 0;
    padding: 2px 8px;
    line-height: 1.15;
    text-align: left;
  }
  .edit {
    min-width: 40px;
    padding: 0 8px;
  }
  .slot {
    font-size: 0.75rem;
    color: inherit;
  }
  .strip.muted {
    /* Muted: red diagonal hatching (the name keeps its channel colour, which can itself be
       red). */
    background-image: repeating-linear-gradient(
      -45deg,
      rgb(255 77 94 / 0.3) 0 4px, /* --danger at 30 % */
      transparent 4px 16px
    );
  }
</style>
