<script lang="ts">
  // Setup wizard, step 2: the plan of the system. The DSP is fixed on the left; amplifiers and
  // speakers are added from the library (or generic), moved by their title, and wired: DSP
  // output → amplifier channel → speaker section (or straight to an active speaker). A wire is
  // drawn by dragging from a port to another, or by tapping one port then the other. Tapping
  // an element opens its properties on the right (below on a phone).
  import {
    addAmp,
    addSpeaker,
    AMPLIFIERS,
    connect,
    orderedWays,
    outputNames,
    parsePort,
    portKey,
    routeOf,
    sourceInputs,
    SPEAKERS,
    wireBetween,
    wiring,
    type Port,
    type Topology,
    type Wire,
  } from "../lib/setup";
  import { wizard } from "../lib/wizard.svelte";
  import SetupProps, { type Selection } from "./SetupProps.svelte";

  let { topo }: { topo: Topology } = $props();

  // Geometry of the plan (px): every port's place is computed from these.
  const W = 150;
  const HEAD = 30;
  const ROW = 26;
  const IN_ROW = 18;
  const DSP_X = 8;
  const DSP_Y = 8;
  const COLORS = ["#3ddc97", "#4da3ff", "#ffb020", "#c38bff", "#ff7a59", "#5ad1e6", "#e6d75a", "#ff5fa2"];

  const draft = $derived(wizard.draft);
  const wired = $derived(wiring(draft, topo));
  const dspOutTop = $derived(DSP_Y + HEAD + topo.inputs * IN_ROW + 8);
  const dspHeight = $derived(dspOutTop - DSP_Y + topo.outputs * ROW + 6);
  // A colour per way: main ways from low to high, then the auxiliary ones.
  const wayColor = $derived(
    new Map(orderedWays(wired.ways).map((w, i) => [w.key, COLORS[i % COLORS.length]!])),
  );
  const names = $derived.by(() => {
    const map = new Map<number, string>();
    for (const way of wired.ways) for (const [o, n] of outputNames(way, wired.sideOf)) map.set(o, n);
    return map;
  });
  const SIDE_LABEL = { L: "L", R: "R", LR: "L+R" } as const;
  const sourceName = (id: number | null) => draft.sources.find((s) => s.id === id)?.name ?? "?";
  /** Name of the source channel on each DSP input. */
  const inputLabels = $derived.by(() => {
    const labels = new Map<number, string>();
    const inputsOf = sourceInputs(draft);
    for (const source of draft.sources)
      (inputsOf.get(source.id) ?? []).forEach((i, k) =>
        labels.set(i, source.stereo ? `${source.name} ${k === 0 ? "L" : "R"}` : source.name),
      );
    return labels;
  });

  function portXY(p: Port): { x: number; y: number } {
    if (p.node === "dsp") return { x: DSP_X + W, y: dspOutTop + p.port * ROW + ROW / 2 };
    if (p.node === "spk") {
      const s = draft.speakers.find((n) => n.id === p.id);
      return { x: s?.x ?? 0, y: (s?.y ?? 0) + HEAD + p.port * ROW + ROW / 2 };
    }
    const a = draft.amps.find((n) => n.id === p.id);
    return {
      x: (a?.x ?? 0) + (p.node === "amp-out" ? W : 0),
      y: (a?.y ?? 0) + HEAD + p.port * ROW + ROW / 2,
    };
  }

  function ends(w: Wire): [Port, Port] {
    if (w.type === "feed")
      return [{ node: "dsp", port: w.output }, { node: "amp-in", id: w.amp, port: w.channel }];
    if (w.type === "drive")
      return [
        { node: "amp-out", id: w.amp, port: w.channel },
        { node: "spk", id: w.speaker, port: w.section },
      ];
    return [{ node: "dsp", port: w.output }, { node: "spk", id: w.speaker, port: w.section }];
  }

  function wireColor(w: Wire): string {
    if (w.type === "drive") {
      const name = draft.speakers.find((s) => s.id === w.speaker)?.sections[w.section]?.name;
      return wayColor.get(name ?? "") ?? "#888";
    }
    return wayColor.get(wired.wayOf.get(w.output) ?? "") ?? "#888";
  }

  const curve = (a: { x: number; y: number }, b: { x: number; y: number }) => {
    const dx = Math.max(40, Math.abs(b.x - a.x) / 2);
    return `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
  };

  const ampHeight = (channels: number) => HEAD + channels * ROW + 6;
  const spkHeight = (sections: number) => HEAD + sections * ROW + 6;
  const size = $derived.by(() => {
    let w = 760;
    let h = DSP_Y + dspHeight + 16;
    for (const a of draft.amps) {
      w = Math.max(w, a.x + W + 40);
      h = Math.max(h, a.y + ampHeight(a.channels) + 40);
    }
    for (const s of draft.speakers) {
      w = Math.max(w, s.x + W + 40);
      h = Math.max(h, s.y + spkHeight(s.sections.length) + 40);
    }
    return { w, h };
  });

  // --- selection and adding -------------------------------------------------------------------
  let selection = $state<Selection | null>(null);
  let speakerPick = $state("");
  let ampPick = $state("");

  function nextY(nodes: { y: number }[], height: number): number {
    return nodes.reduce((y, n) => Math.max(y, n.y + height + 10), DSP_Y);
  }

  // New blocks: amplifiers in a column right of the DSP, speakers in columns further right
  // (a new column every 6 speakers).
  const AMP_X = DSP_X + W + 70;
  const SPK_X = AMP_X + W + 130;
  const SPK_COLUMN = 6;

  function addSpeakerNode() {
    const n = draft.speakers.length;
    const column = Math.floor(n / SPK_COLUMN);
    const same = draft.speakers.slice(column * SPK_COLUMN);
    const y = same.length ? nextY(same, spkHeight(2)) : DSP_Y;
    const node = addSpeaker(draft, speakerPick || null, SPK_X + column * (W + 30), y);
    selection = { type: "speaker", id: node.id };
  }

  function addAmpNode() {
    const y = draft.amps.reduce((max, a) => Math.max(max, a.y + ampHeight(a.channels) + 14), DSP_Y);
    const node = addAmp(draft, ampPick || null, AMP_X, y);
    selection = { type: "amp", id: node.id };
  }

  // --- dragging nodes ---------------------------------------------------------------------------
  let moving: { type: "amp" | "speaker"; id: number; dx: number; dy: number; moved: boolean; x0: number; y0: number } | null = null;

  function startMove(e: PointerEvent, type: "amp" | "speaker", id: number) {
    const node = type === "amp" ? draft.amps.find((a) => a.id === id) : draft.speakers.find((s) => s.id === id);
    if (!node) return;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    moving = { type, id, dx: e.clientX - node.x, dy: e.clientY - node.y, moved: false, x0: e.clientX, y0: e.clientY };
  }

  function move(e: PointerEvent) {
    if (!moving) return;
    if (Math.hypot(e.clientX - moving.x0, e.clientY - moving.y0) > 4) moving.moved = true;
    if (!moving.moved) return;
    const m = moving;
    const node = m.type === "amp" ? draft.amps.find((a) => a.id === m.id) : draft.speakers.find((s) => s.id === m.id);
    if (!node) return;
    node.x = Math.max(DSP_X + W + 16, Math.round(e.clientX - m.dx));
    node.y = Math.max(4, Math.round(e.clientY - m.dy));
  }

  function endMove() {
    if (moving && !moving.moved) selection = { type: moving.type, id: moving.id };
    moving = null;
  }

  // --- wiring -----------------------------------------------------------------------------------
  let canvas = $state<HTMLDivElement>();
  /** A port tapped, waiting for the other end. */
  let pending = $state<Port | null>(null);
  let drawing = $state<{ from: Port; x: number; y: number; moved: boolean; x0: number; y0: number } | null>(null);

  function local(e: PointerEvent): { x: number; y: number } {
    const box = canvas!.getBoundingClientRect();
    return { x: e.clientX - box.left, y: e.clientY - box.top };
  }

  function startWire(e: PointerEvent, port: Port) {
    e.stopPropagation();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    const p = local(e);
    drawing = { from: port, ...p, moved: false, x0: e.clientX, y0: e.clientY };
  }

  function moveWire(e: PointerEvent) {
    if (!drawing) return;
    if (Math.hypot(e.clientX - drawing.x0, e.clientY - drawing.y0) > 6) drawing.moved = true;
    const p = local(e);
    drawing.x = p.x;
    drawing.y = p.y;
  }

  function join(a: Port, b: Port): boolean {
    const wire = wireBetween(a, b);
    if (!wire) return false;
    connect(draft, wire);
    selection = { type: "wire", wire };
    return true;
  }

  function endWire(e: PointerEvent) {
    if (!drawing) return;
    const from = drawing.from;
    if (drawing.moved) {
      const target = document.elementFromPoint(e.clientX, e.clientY)?.closest<HTMLElement>("[data-port]");
      const to = target ? parsePort(target.dataset.port ?? "") : null;
      if (to) join(from, to);
      pending = null;
    } else if (pending && portKey(pending) !== portKey(from) && join(pending, from)) {
      pending = null;
    } else {
      pending = pending && portKey(pending) === portKey(from) ? null : from; // tap: wait for the other end
    }
    drawing = null;
  }

  /** Ports the pending (or drawn) wire can end on. */
  function canJoin(p: Port): boolean {
    const from = drawing?.from ?? pending;
    return from !== null && wireBetween(from, p) !== null;
  }

  function clickBackground(e: MouseEvent) {
    if (e.target === canvas || (e.target as Element).tagName === "svg") {
      selection = null;
      pending = null;
    }
  }

  const isSelected = (type: string, id: number) =>
    selection !== null && selection.type === type && "id" in selection && selection.id === id;
</script>

{#snippet port(p: Port, side: "left" | "right")}
  <span
    class="port {side}"
    class:pending={pending !== null && portKey(pending) === portKey(p)}
    class:target={canJoin(p)}
    data-port={portKey(p)}
    role="button"
    tabindex="-1"
    aria-label="Port"
    onpointerdown={(e) => startWire(e, p)}
    onpointermove={moveWire}
    onpointerup={endWire}
    onpointercancel={() => (drawing = null)}
  ></span>
{/snippet}

<div class="layout">
  <section class="card plan-card">
    <div class="toolbar">
      <div class="add">
        <select aria-label="Speaker to add" bind:value={speakerPick}>
          <option value="">Generic speaker</option>
          {#each SPEAKERS as m (m.id)}<option value={m.id}>{m.name} — {m.description}</option>{/each}
        </select>
        <button class="primary" onclick={addSpeakerNode}>+ Speaker</button>
      </div>
      <div class="add">
        <select aria-label="Amplifier to add" bind:value={ampPick}>
          <option value="">Generic amplifier</option>
          {#each AMPLIFIERS as a (a.id)}<option value={a.id}>{a.name} ({a.channels} ch)</option>{/each}
        </select>
        <button class="primary" onclick={addAmpNode}>+ Amplifier</button>
      </div>
    </div>
    <p class="muted hint">
      Move a block by its title. Wire a DSP output to an amplifier channel, and the channel to
      its speakers (several in parallel): drag from one dot to the other, or tap one then the
      other. Wire an output straight to an active speaker. Tap a block, an output or a wire to
      edit it.
    </p>
    <div class="scroll">
      <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
      <div
        class="canvas"
        bind:this={canvas}
        style:width={`${size.w}px`}
        style:height={`${size.h}px`}
        onclick={clickBackground}
      >
        <svg width={size.w} height={size.h} aria-hidden="true">
          {#each draft.wires as w (JSON.stringify(w))}
            {@const [a, b] = ends(w)}
            {@const d = curve(portXY(a), portXY(b))}
            {@const selected = selection?.type === "wire" && JSON.stringify(selection.wire) === JSON.stringify(w)}
            <path class="wire" class:selected {d} stroke={wireColor(w)} />
            <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
            <path class="hit" {d} onclick={() => (selection = { type: "wire", wire: w })} />
          {/each}
          {#if drawing?.moved}
            <path class="wire drawing" d={curve(portXY(drawing.from), drawing)} stroke="#fff" />
          {/if}
        </svg>

        <div class="node dsp" style:left={`${DSP_X}px`} style:top={`${DSP_Y}px`} style:height={`${dspHeight}px`}>
          <div class="head fixed">DSP</div>
          {#each Array.from({ length: topo.inputs }, (_, i) => i) as i (i)}
            <div class="in" class:dim={!inputLabels.has(i)}>
              <b>{String.fromCharCode(65 + i)}</b>
              {inputLabels.get(i) ?? "—"}
            </div>
          {/each}
          <div class="outs">
            {#each Array.from({ length: topo.outputs }, (_, o) => o) as o (o)}
              {@const way = wired.wayOf.get(o)}
              {@const side = wired.sideOf.get(o) ?? "LR"}
              <div class="outrow">
                <button
                  class="row out"
                  class:dim={!way}
                  class:selected={selection?.type === "dsp" && selection.output === o}
                  style:--c={wayColor.get(way ?? "")}
                  onclick={() => (selection = { type: "dsp", output: o })}
                >
                  <b>{o + 1}</b>
                  <span class="label">{names.get(o) ?? `Out${o + 1}`}</span>
                  {#if way}<small>{sourceName(routeOf(draft, o))} {SIDE_LABEL[side]}</small>{/if}
                </button>
                {@render port({ node: "dsp", port: o }, "right")}
              </div>
            {/each}
          </div>
        </div>

        {#each draft.amps as amp (amp.id)}
          <div
            class="node amp"
            class:selected={isSelected("amp", amp.id)}
            style:left={`${amp.x}px`}
            style:top={`${amp.y}px`}
            style:height={`${ampHeight(amp.channels)}px`}
          >
            <div
              class="head"
              role="button"
              tabindex="0"
              onpointerdown={(e) => startMove(e, "amp", amp.id)}
              onpointermove={move}
              onpointerup={endMove}
              onkeydown={(e) => e.key === "Enter" && (selection = { type: "amp", id: amp.id })}
            >
              {amp.model}
            </div>
            {#each Array.from({ length: amp.channels }, (_, c) => c) as c (c)}
              <div class="row ch" style:top={`${HEAD + c * ROW}px`}>Ch {c + 1}</div>
              <div class="anchor" style:top={`${HEAD + c * ROW}px`}>
                {@render port({ node: "amp-in", id: amp.id, port: c }, "left")}
                {@render port({ node: "amp-out", id: amp.id, port: c }, "right")}
              </div>
            {/each}
          </div>
        {/each}

        {#each draft.speakers as spk (spk.id)}
          <div
            class="node spk"
            class:selected={isSelected("speaker", spk.id)}
            style:left={`${spk.x}px`}
            style:top={`${spk.y}px`}
            style:height={`${spkHeight(spk.sections.length)}px`}
          >
            <div
              class="head"
              role="button"
              tabindex="0"
              onpointerdown={(e) => startMove(e, "speaker", spk.id)}
              onpointermove={move}
              onpointerup={endMove}
              onkeydown={(e) => e.key === "Enter" && (selection = { type: "speaker", id: spk.id })}
            >
              {#if spk.side !== "LR"}<span class="side">{spk.side}</span>{/if}
              {spk.model}
            </div>
            {#each spk.sections as section, i (i)}
              <div class="row ch" style:top={`${HEAD + i * ROW}px`} style:--c={wayColor.get(section.name)}>
                {section.name}{draft.ways[section.name]?.aux ? " (aux)" : ""}
              </div>
              <div class="anchor" style:top={`${HEAD + i * ROW}px`}>
                {@render port({ node: "spk", id: spk.id, port: i }, "left")}
              </div>
            {/each}
          </div>
        {/each}
      </div>
    </div>
    {#if pending}
      <p class="muted hint">Now tap the other end of the wire (or the same dot to cancel).</p>
    {/if}
  </section>

  <aside class="card props">
    {#if selection}
      <SetupProps {topo} bind:selection />
    {:else}
      <h2>Properties</h2>
      <p class="muted hint">
        Tap a block, a DSP output or a wire to see and change its properties. The ways come from
        the wiring, by channel name: the outputs that drive sections called "Sub" form the Sub
        way, their outputs linked (two outputs to four subs: one Sub way). Each speaker is left,
        right or mono (L+R): its outputs play that side.
      </p>
      {#if wired.ways.length}
        <h3>Ways</h3>
        <ul class="ways">
          {#each orderedWays(wired.ways) as way (way.key)}
            <li style:--c={wayColor.get(way.key)}>
              <b>{way.key}</b>
              {way.outputs.map((o) => `Out ${o + 1}`).join(", ")} · {way.cabinets} cabinet{way.cabinets > 1 ? "s" : ""}{way.active ? " · active" : ""}
            </li>
          {/each}
        </ul>
      {/if}
    {/if}
  </aside>
</div>

<style>
  .layout {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
  }
  @media (min-width: 1000px) {
    .layout {
      grid-template-columns: minmax(0, 1fr) 340px;
      align-items: start;
    }
    .props {
      position: sticky;
      top: 0;
      max-height: calc(100vh - 20px);
      overflow: auto;
    }
  }
  .toolbar {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(280px, 100%), 1fr));
    gap: 8px;
  }
  .add {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 6px;
  }
  .hint {
    font-size: 0.8rem;
    margin: 8px 0;
  }
  .scroll {
    overflow: auto;
    max-height: 75vh;
    border: 1px solid var(--line);
    border-radius: 8px;
    background: #0d0f13;
  }
  .canvas {
    position: relative;
    background-image: radial-gradient(#ffffff14 1px, transparent 1px);
    background-size: 20px 20px;
  }
  svg {
    position: absolute;
    inset: 0;
  }
  .wire {
    fill: none;
    stroke-width: 2.5;
    pointer-events: none;
  }
  .wire.selected {
    stroke-width: 5;
  }
  .wire.drawing {
    stroke-dasharray: 6 4;
  }
  .hit {
    fill: none;
    stroke: transparent;
    stroke-width: 14;
    pointer-events: stroke;
    cursor: pointer;
  }
  .node {
    position: absolute;
    width: 150px;
    border-radius: 8px;
    background: var(--panel-2);
    box-shadow: 0 0 0 1.5px var(--line);
    font-size: 0.8rem;
  }
  .node.selected {
    box-shadow: 0 0 0 2px var(--accent);
  }
  .head {
    height: 30px;
    line-height: 30px;
    padding: 0 8px;
    font-weight: 700;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    box-shadow: inset 0 -1px 0 var(--line);
    cursor: grab;
    touch-action: none;
    user-select: none;
    border-radius: 8px 8px 0 0;
  }
  .head.fixed {
    cursor: default;
  }
  .dsp .head {
    background: color-mix(in srgb, var(--accent) 18%, transparent);
  }
  .in {
    height: 18px;
    line-height: 18px;
    padding: 0 8px;
    font-size: 0.72rem;
    white-space: nowrap;
    overflow: hidden;
  }
  .outs {
    margin-top: 8px;
    box-shadow: 0 -1px 0 var(--line);
  }
  .outrow {
    position: relative;
    height: 26px;
  }
  .row {
    height: 26px;
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 0 8px;
    white-space: nowrap;
    overflow: hidden;
  }
  .row.out {
    width: 100%;
    min-height: 0;
    border: 0;
    border-radius: 0;
    background: transparent;
    font: inherit;
    font-size: 0.8rem;
    text-align: left;
    box-shadow: inset 3px 0 0 var(--c, transparent);
  }
  .row.out.selected {
    background: color-mix(in srgb, var(--accent) 22%, transparent);
  }
  .row .label {
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .row small {
    color: var(--muted);
    font-size: 0.68rem;
  }
  .ch {
    position: absolute;
    left: 0;
    right: 0;
    justify-content: center;
    box-shadow: inset 0 -2px 0 var(--c, transparent);
  }
  .anchor {
    position: absolute;
    left: 0;
    right: 0;
    height: 26px;
    pointer-events: none;
  }
  .port {
    position: absolute;
    top: 0;
    width: 24px;
    height: 26px;
    pointer-events: auto;
    touch-action: none;
    cursor: crosshair;
  }
  .port.left {
    left: -12px;
  }
  .port.right {
    right: -12px;
  }
  .port::after {
    content: "";
    position: absolute;
    left: 6px;
    top: 7px;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    background: var(--panel);
    border: 2px solid var(--muted);
    box-sizing: border-box;
  }
  .port.target::after {
    border-color: var(--accent);
    background: color-mix(in srgb, var(--accent) 40%, var(--panel));
  }
  .port.pending::after {
    background: var(--accent);
    border-color: #fff;
  }
  .dim {
    opacity: 0.45;
  }
  .side {
    display: inline-block;
    min-width: 18px;
    margin-right: 6px;
    border-radius: 4px;
    background: var(--info);
    color: #000;
    text-align: center;
    font-size: 0.7rem;
    line-height: 18px;
  }
  .ways {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 4px;
    font-size: 0.85rem;
  }
  .ways li {
    padding-left: 8px;
    box-shadow: inset 3px 0 0 var(--c);
  }
  h3 {
    font-size: 0.95rem;
    margin: 12px 0 6px;
  }
</style>
