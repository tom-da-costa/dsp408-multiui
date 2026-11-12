<script lang="ts">
  // "All-in-one" tab: one column per channel with the settings picked in the chip row, for the
  // channels picked in the row below (as in the Live tab). Both are remembered in this browser.
  // The blocks follow the order a system is set up in (name, link, routing, crossover, dynamics,
  // gain, EQ, delay, then the input-only gate and GEQ). MUTE sits under the meter of each column.
  import { app } from "../lib/app.svelte";
  import { links } from "../lib/links.svelte";
  import { nav, PARAM_SCOPE, PARAMS, slotLabel, type Param } from "../lib/nav.svelte";
  import { ChannelSelection } from "../lib/selection.svelte";
  import ChannelPicker from "./ChannelPicker.svelte";
  import ChipBar from "./ChipBar.svelte";
  import LevelBar from "./LevelBar.svelte";
  import NameEditor from "./NameEditor.svelte";
  import ParamBlock from "./ParamBlock.svelte";
  import Section from "./Section.svelte";
  import SideDivider from "./SideDivider.svelte";

  /** A block of a column: the channel name or a setting of the Params tab. */
  type Item = "name" | Param;
  const ORDER: Item[] = [
    "name",
    "link",
    "matrix",
    "filters",
    "comp",
    "limit",
    "gain",
    "eq",
    "delay",
    "gate",
    "geq",
  ];
  const LABELS = Object.fromEntries([["name", "Name"], ...PARAMS]) as Record<Item, string>;
  const ITEMS = ORDER.map((key) => [key, LABELS[key]] as const);

  const STORAGE_KEY = "dsp408.aio.params";
  // Everything but the input-only gate and GEQ, which are set less often.
  const DEFAULT: Item[] = ORDER.filter((key) => key !== "gate" && key !== "geq");

  function load(): Item[] {
    try {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null") as unknown;
      if (Array.isArray(saved)) return ORDER.filter((k) => saved.includes(k));
    } catch {
      // storage unavailable or corrupt: use the default
    }
    return DEFAULT;
  }

  let shown = $state<Item[]>(load());

  function toggle(key: string) {
    const item = key as Item;
    // Keep the ITEMS order whatever the click order.
    shown = ORDER.filter((k) => (k === item ? !shown.includes(k) : shown.includes(k)));
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(shown));
    } catch {
      // not persisted: fine
    }
  }

  const selection = new ChannelSelection("dsp408.aio.hidden");
  const device = $derived(app.device);
  function channelAt(path: string) {
    const [side, n] = path.split(".");
    return (side === "inputs" ? device?.inputs : device?.outputs)?.[Number(n)];
  }
  const channels = $derived(
    selection.shown.flatMap((path) => {
      const channel = channelAt(path);
      return channel ? [{ path, channel }] : [];
    }),
  );

  function linkedWith(path: string): string {
    const [side] = path.split(".");
    const others = (channelAt(path)?.linked ?? []).map((i) => slotLabel(`${side}.${i}`));
    return others.join(", ");
  }

  function applies(item: Item, path: string): boolean {
    if (item === "name") return true;
    const scope = PARAM_SCOPE[item];
    return scope === "all" || path.startsWith(scope);
  }
</script>

<ChipBar
  items={ITEMS.map(([key, label]) => ({ key, label }))}
  selected={shown}
  onselect={toggle}
  label="Settings shown"
/>
<ChannelPicker {selection} />

<div class="strips">
  {#each channels as { path, channel }, i (path)}
    {#if i > 0 && path.startsWith("outputs.") && channels[i - 1]?.path.startsWith("inputs.")}
      <SideDivider />
    {/if}
    <section class="strip" class:muted={channel.mute} style:--ch={app.color(path)}>
      <button class="head" onclick={() => nav.open(path)} title="Open this channel">
        <span class="slot">{links.slot(path)}{links.mark(path)}</span>
        <strong>{links.name(path)}</strong>
      </button>
      <LevelBar {path} compact indicators />
      <button
        class="switch danger mute"
        class:on={channel.mute}
        disabled={!app.editable("mute")}
        aria-pressed={channel.mute}
        onclick={() => app.set(`${path}.mute`, !channel.mute)}>Mute</button
      >
      {#each shown.filter((item) => applies(item, path)) as item (item)}
        {@const members = links.members(path)}
        {#if item === "name"}
          <!-- Names stay per channel: one field per member of a merged group. -->
          <Section id={`name@${path}`} title="Name" kind="name">
            {#each members as member (member)}
              {@const memberChannel = channelAt(member)}
              {#if memberChannel}
                <NameEditor
                  channel={memberChannel}
                  path={member}
                  label={members.length > 1 ? slotLabel(member) : ""}
                />
              {/if}
            {/each}
          </Section>
        {:else if item === "link"}
          <!-- Links are edited for a whole side at once, in Params › Link. -->
          <Section id={`link@${path}`} title="Link" kind="link">
            <div class="link">
              <span class:muted={!channel.linked.length}>
                {channel.linked.length ? `🔗 Linked with ${linkedWith(path)}` : "Not linked"}
              </span>
              <button onclick={() => nav.selectParam("link")}>Edit links</button>
            </div>
          </Section>
        {:else if item === "matrix" && members.length > 1}
          <!-- So does the routing: one block per member. -->
          {#each members as member (member)}
            <ParamBlock param="matrix" path={member} title={`Matrix · ${slotLabel(member)}`} />
          {/each}
        {:else}
          <ParamBlock param={item} {path} mute={false} />
        {/if}
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
  .mute {
    width: 100%;
  }
  .link {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
  }
  .strip :global(section.card) {
    margin: 0;
    background: var(--panel-2);
  }
  .head {
    border: 2px solid var(--ch);
    color: var(--ch);
    display: grid;
    justify-items: start;
    min-height: 40px;
    padding: 2px 8px;
    line-height: 1.15;
    text-align: left;
    background: none;
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
