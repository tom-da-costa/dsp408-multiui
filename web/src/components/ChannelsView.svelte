<script lang="ts">
  // "Channels" tab: one sub-tab per channel, each showing all of its settings.
  import { app } from "../lib/app.svelte";
  import { nav, slotLabel } from "../lib/nav.svelte";
  import ChannelDetail from "./ChannelDetail.svelte";
  import ChipBar from "./ChipBar.svelte";

  const device = $derived(app.device);
  const items = $derived([
    ...(device?.inputs ?? []).map((c, i) => ({ path: `inputs.${i}`, name: c.name })),
    ...(device?.outputs ?? []).map((c, i) => ({ path: `outputs.${i}`, name: c.name })),
  ].map(({ path, name }) => ({ key: path, label: slotLabel(path), sub: name })));
</script>

<ChipBar {items} selected={nav.channel} onselect={(p) => nav.selectChannel(p)} label="Channel" />
<ChannelDetail path={nav.channel} />
