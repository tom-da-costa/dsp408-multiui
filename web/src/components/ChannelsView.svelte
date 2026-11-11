<script lang="ts">
  // "Channels" tab: one sub-tab per channel (per link group with "Merge linked channels"), each
  // showing all of its settings.
  import { app } from "../lib/app.svelte";
  import { links } from "../lib/links.svelte";
  import { nav } from "../lib/nav.svelte";
  import ChannelDetail from "./ChannelDetail.svelte";
  import ChipBar from "./ChipBar.svelte";

  const device = $derived(app.device);
  const items = $derived([
    ...(device?.inputs ?? []).map((c, i) => ({ path: `inputs.${i}`, name: c.name })),
    ...(device?.outputs ?? []).map((c, i) => ({ path: `outputs.${i}`, name: c.name })),
  ]
    .filter(({ path }) => links.isShown(path))
    .map(({ path }) => ({
      key: path,
      label: links.slot(path),
      sub: links.name(path),
      color: app.color(path),
    })));
  // A merged member (from a link or the URL) opens its group's lead.
  const current = $derived(links.lead(nav.channel));
</script>

<ChipBar {items} selected={current} onselect={(p) => nav.selectChannel(p)} label="Channel" />
<ChannelDetail path={current} />
