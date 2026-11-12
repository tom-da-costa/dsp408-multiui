<script lang="ts">
  // One numeric parameter: label, value (tap to type), − / + steppers and a knob-drag slider.
  // A row with a horizontal slider, or a column with a vertical one (lib/layout.ts).
  import type { Snippet } from "svelte";
  import { inStrip } from "../lib/layout";
  import { holdRepeat } from "../lib/repeat";
  import { throttleLatest } from "../lib/throttle";
  import { type Direction, parseNumber, type Scale, snap } from "../lib/scale";
  import Slider from "./Slider.svelte";

  interface Props {
    label: string;
    value: number;
    min: number;
    max: number;
    unit?: string;
    /** Stepper increment: the device's resolution, unless `next` is given. */
    step?: number;
    /** One device step from `value` (values the device does not store on a uniform grid). */
    next?: (value: number, direction: Direction) => number;
    /** Values are rounded to a multiple of this; omit to only clamp (the server quantises). */
    resolution?: number;
    scale?: Scale;
    digits?: number;
    origin?: number;
    format?: (value: number) => string;
    slider?: boolean;
    disabled?: boolean;
    after?: Snippet;
    onchange: (value: number) => void;
  }

  let {
    label,
    value,
    min,
    max,
    unit = "",
    step = 1,
    next,
    resolution,
    scale = "lin",
    digits = 1,
    origin,
    format,
    slider = true,
    disabled = false,
    after,
    onchange,
  }: Props = $props();

  const vertical = inStrip();

  let preview = $state<number | null>(null);
  let editing = $state(false);
  let draft = $state("");

  /** Value sent by − / + that the device has not confirmed yet (see stepBy). */
  let pending = $state<number | null>(null);
  let settle: ReturnType<typeof setTimeout> | undefined;
  const shown = $derived(preview ?? pending ?? value);
  const display = (v: number) => (format ? format(v) : v.toFixed(digits));
  const text = $derived(display(shown));
  const quantize = (v: number) => snap(v, min, max, resolution);

  // − / + (held: auto-repeat) and the slider's arrow keys: `count` device steps. Steps chain
  // from the last value sent, not from `value`, which only follows once the DSP has answered;
  // the field shows that pending value until the device's value catches up.

  function stepBy(count: number) {
    if (disabled || count === 0) return;
    const direction: Direction = count > 0 ? 1 : -1;
    const from = pending ?? value;
    let target = from;
    for (let i = 0; i < Math.abs(count); i++) {
      target = next ? next(target, direction) : target + direction * step;
    }
    const q = next ? Math.min(max, Math.max(min, target)) : quantize(target);
    if (q === from) return;
    pending = q;
    clearTimeout(settle);
    settle = setTimeout(() => (pending = null), 2000); // never stay stuck on a refused value
    sender.push(q);
  }

  // A held − / + shows every step at once but sends at most every 500 ms (the latest value).
  const sender = throttleLatest((v: number) => onchange(v), 500);

  $effect(() => {
    // The device reached the value we sent: show it again.
    // (Compared as displayed: the server rounds, e.g. Hz to 2 decimals.)
    if (pending !== null && display(value) === display(pending)) pending = null;
  });

  function startEdit() {
    if (disabled) return;
    draft = shown.toFixed(digits);
    editing = true;
  }

  function commit(event: SubmitEvent) {
    event.preventDefault();
    const v = parseNumber(draft);
    if (v !== null) onchange(quantize(v));
    editing = false;
  }
</script>

{#snippet minus()}
  <button
    class="step minus"
    use:holdRepeat={{ step: () => stepBy(-1), end: () => sender.flush(), disabled }}
    {disabled}
    aria-label={`${label} down (hold to repeat)`}>−</button
  >
{/snippet}

{#snippet plus()}
  <button
    class="step plus"
    use:holdRepeat={{ step: () => stepBy(1), end: () => sender.flush(), disabled }}
    {disabled}
    aria-label={`${label} up (hold to repeat)`}>+</button
  >
{/snippet}

{#snippet valueBox()}
  {#if editing}
    <form onsubmit={commit} class="value">
      <!-- svelte-ignore a11y_autofocus -->
      <input
        type="text"
        inputmode="decimal"
        enterkeyhint="done"
        bind:value={draft}
        onblur={() => (editing = false)}
        onfocus={(e) => e.currentTarget.select()}
        autofocus
        aria-label={`${label}${unit ? ` in ${unit}` : ""}`}
      />
    </form>
  {:else}
    <button class="value" onclick={startEdit} {disabled} aria-label={`${label}: ${text} ${unit}, tap to type`}>
      <span class="num">{text}</span>{#if unit}<span class="unit">{unit}</span>{/if}
    </button>
  {/if}
{/snippet}

{#snippet slide()}
  <div class="slide">
    <Slider
      {value}
      {min}
      {max}
      {scale}
      {origin}
      {vertical}
      {disabled}
      {quantize}
      {label}
      onstep={stepBy}
      onpreview={(v) => (preview = v)}
      {onchange}
    />
  </div>
{/snippet}

{#if vertical}
  <div class="vfield" class:disabled>
    <span class="label">{label}</span>
    {@render valueBox()}
    {@render plus()}
    {#if slider}{@render slide()}{/if}
    {@render minus()}
    {#if after}<div class="after">{@render after()}</div>{/if}
  </div>
{:else}
  <div class="wrap">
    <div class="field" class:disabled class:noslider={!slider}>
      <span class="label">{label}</span>
      {@render minus()}
      {@render valueBox()}
      {@render plus()}
      {#if slider}{@render slide()}{/if}
      {#if after}<div class="after">{@render after()}</div>{/if}
    </div>
  </div>
{/if}

<style>
  .wrap {
    container-type: inline-size;
  }
  .field {
    display: grid;
    grid-template-columns: 1fr 40px minmax(84px, auto) 40px;
    grid-template-areas: "label minus value plus" "slide slide slide slide" "after after after after";
    align-items: center;
    gap: 2px 6px;
    padding: 4px 0;
  }
  .label {
    grid-area: label;
    color: var(--muted);
    font-size: 0.9rem;
  }
  .minus {
    grid-area: minus;
  }
  .plus {
    grid-area: plus;
  }
  .step {
    min-height: 36px;
    padding: 0;
    font-size: 1.1rem;
  }
  .value {
    grid-area: value;
    min-height: 36px;
    padding: 0 8px;
    font-variant-numeric: tabular-nums;
    /* A button centres its content vertically; number and unit stay on one baseline and the
       unit wraps under the number when the box is too narrow (inline blocks). */
    text-align: center;
    line-height: 1.15;
  }
  .num,
  .unit {
    display: inline-block;
  }
  .unit {
    margin-left: 3px;
    color: var(--muted);
    font-size: 0.8rem;
  }
  form.value {
    padding: 0;
  }
  form input {
    width: 84px;
    min-height: 36px;
    text-align: center;
  }
  .slide {
    grid-area: slide;
    margin: 0 -10px;
  }
  .after {
    grid-area: after;
    color: var(--muted);
    font-size: 0.8rem;
  }
  .disabled .label {
    opacity: 0.6;
  }
  /* vertical: label, value, +, slider, − in a column (Params tab) */
  .vfield {
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 4px;
    min-width: 0;
  }
  .vfield .label {
    text-align: center;
    font-size: 0.8rem;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .vfield .value {
    padding: 0 2px;
    font-size: 0.9rem;
  }
  .vfield .unit {
    margin-left: 2px;
    font-size: 0.7rem;
  }
  .vfield form input {
    width: 100%;
  }
  .vfield .slide {
    flex: 1 1 0; /* the slider takes the height left */
    min-height: 90px;
    margin: 0;
    display: flex;
    justify-content: center;
  }
  /* wide containers: slider on the same row */
  @container (min-width: 460px) {
    .field:not(.noslider) {
      grid-template-columns: 120px 1fr 40px minmax(84px, auto) 40px;
      grid-template-areas: "label slide minus value plus" ". after after after after";
    }
  }
</style>
