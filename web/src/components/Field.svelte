<script lang="ts">
  // One numeric parameter: label, value (tap to type), − / + steppers and a knob-drag slider.
  import type { Snippet } from "svelte";
  import { parseNumber, type Scale, snap } from "../lib/scale";
  import Slider from "./Slider.svelte";

  interface Props {
    label: string;
    value: number;
    min: number;
    max: number;
    unit?: string;
    /** Stepper increment; with `factor`, the minimum increment of a multiplicative step. */
    step?: number;
    /** Multiplicative stepper (log-scaled values such as Hz or Q). */
    factor?: number;
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
    factor,
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

  let preview = $state<number | null>(null);
  let editing = $state(false);
  let draft = $state("");

  const shown = $derived(preview ?? value);
  const text = $derived(format ? format(shown) : shown.toFixed(digits));
  const quantize = (v: number) => snap(v, min, max, resolution);

  function stepBy(direction: number) {
    if (disabled) return;
    let next = value;
    for (let i = 0; i < Math.abs(direction); i++) {
      const up = direction > 0;
      if (factor) next = up ? Math.max(next + step, next * factor) : Math.min(next - step, next / factor);
      else next = next + (up ? step : -step);
    }
    const q = quantize(next);
    if (q !== value) onchange(q);
  }

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

<div class="wrap">
<div class="field" class:disabled class:noslider={!slider}>
  <span class="label">{label}</span>
  <button class="step minus" onclick={() => stepBy(-1)} {disabled} aria-label={`${label} down`}
    >−</button
  >
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
  <button class="step plus" onclick={() => stepBy(1)} {disabled} aria-label={`${label} up`}>+</button>
  {#if slider}
    <div class="slide">
      <Slider
        {value}
        {min}
        {max}
        {scale}
        {origin}
        {disabled}
        {quantize}
        {label}
        onstep={stepBy}
        onpreview={(v) => (preview = v)}
        {onchange}
      />
    </div>
  {/if}
  {#if after}<div class="after">{@render after()}</div>{/if}
</div>
</div>

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
    display: flex;
    align-items: baseline;
    justify-content: center;
    gap: 3px;
  }
  .unit {
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
  /* wide containers: slider on the same row */
  @container (min-width: 460px) {
    .field:not(.noslider) {
      grid-template-columns: 120px 1fr 40px minmax(84px, auto) 40px;
      grid-template-areas: "label slide minus value plus" ". after after after after";
    }
  }
</style>
