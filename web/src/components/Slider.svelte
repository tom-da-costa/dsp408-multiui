<script lang="ts">
  // A slider that only moves on a drag starting on its knob (scrolling never changes a value).
  import { fromPos, type Scale, toPos } from "../lib/scale";
  import { throttleLatest } from "../lib/throttle";

  interface Props {
    value: number;
    min: number;
    max: number;
    label: string;
    scale?: Scale;
    /** Value the fill starts from (e.g. 0 dB for an EQ gain); defaults to `min`. */
    origin?: number;
    vertical?: boolean;
    disabled?: boolean;
    quantize?: (value: number) => number;
    /** Keyboard arrows: called with +1 / -1 (PageUp/PageDown: +10 / -10). */
    onstep?: (direction: number) => void;
    /** Called while dragging with the local value, then with null on release. */
    onpreview?: (value: number | null) => void;
    onchange: (value: number) => void;
  }

  let {
    value,
    min,
    max,
    label,
    scale = "lin",
    origin,
    vertical = false,
    disabled = false,
    quantize = (v: number) => v,
    onstep,
    onpreview,
    onchange,
  }: Props = $props();

  let track: HTMLDivElement | undefined = $state();
  let dragging = $state(false);
  let local = $state(0);

  const shown = $derived(dragging ? local : value);
  const pos = $derived(toPos(shown, min, max, scale));
  const originPos = $derived(toPos(origin ?? min, min, max, scale));
  const fillStart = $derived(Math.min(pos, originPos) * 100);
  const fillSize = $derived(Math.abs(pos - originPos) * 100);
  const sender = throttleLatest((v: number) => onchange(v), 50);

  function fromPointer(event: PointerEvent): number {
    if (!track) return value;
    const rect = track.getBoundingClientRect();
    const p = vertical
      ? 1 - (event.clientY - rect.top) / rect.height
      : (event.clientX - rect.left) / rect.width;
    return quantize(fromPos(p, min, max, scale));
  }

  function down(event: PointerEvent) {
    if (disabled) return;
    event.preventDefault();
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
    dragging = true;
    local = value;
  }

  function move(event: PointerEvent) {
    if (!dragging) return;
    const v = fromPointer(event);
    if (v !== local) {
      local = v;
      onpreview?.(v);
      sender.push(v);
    }
  }

  function up() {
    if (!dragging) return;
    sender.flush();
    dragging = false;
    onpreview?.(null);
  }

  function key(event: KeyboardEvent) {
    if (disabled || !onstep) return;
    const steps: Record<string, number> = {
      ArrowUp: 1,
      ArrowRight: 1,
      ArrowDown: -1,
      ArrowLeft: -1,
      PageUp: 10,
      PageDown: -10,
    };
    const step = steps[event.key];
    if (step !== undefined) {
      event.preventDefault();
      onstep(step);
    }
  }
</script>

<div class="slider" class:vertical class:disabled>
  <div class="track" bind:this={track}>
    {#if vertical}
      <div class="fill" style:bottom={`${fillStart}%`} style:height={`${fillSize}%`}></div>
      {#if origin !== undefined}<div class="origin" style:bottom={`${originPos * 100}%`}></div>{/if}
    {:else}
      <div class="fill" style:left={`${fillStart}%`} style:width={`${fillSize}%`}></div>
      {#if origin !== undefined}<div class="origin" style:left={`${originPos * 100}%`}></div>{/if}
    {/if}
    <div
      class="knob"
      class:active={dragging}
      style={vertical ? `bottom: ${pos * 100}%` : `left: ${pos * 100}%`}
      role="slider"
      tabindex={disabled ? -1 : 0}
      aria-label={label}
      aria-orientation={vertical ? "vertical" : "horizontal"}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={shown}
      aria-disabled={disabled}
      onpointerdown={down}
      onpointermove={move}
      onpointerup={up}
      onpointercancel={up}
      onkeydown={key}
    ></div>
  </div>
</div>

<style>
  .slider {
    display: flex;
    align-items: center;
    height: 40px;
    padding: 0 16px;
  }
  .track {
    position: relative;
    flex: 1;
    height: 6px;
    border-radius: 3px;
    background: #0b0c0f;
  }
  .fill {
    position: absolute;
    top: 0;
    bottom: 0;
    border-radius: 3px;
    background: color-mix(in srgb, var(--accent) 55%, transparent);
  }
  .origin {
    position: absolute;
    top: -6px;
    bottom: -6px;
    width: 1px;
    background: var(--muted);
  }
  .knob {
    position: absolute;
    top: 50%;
    width: 30px;
    height: 30px;
    margin: -15px 0 0 -15px;
    border-radius: 50%;
    background: linear-gradient(#4a505c, #2d323b);
    border: 1px solid #5d6573;
    touch-action: none;
    cursor: grab;
  }
  .knob::after {
    content: "";
    position: absolute;
    inset: 11px;
    border-radius: 50%;
    background: var(--accent);
  }
  .knob.active {
    cursor: grabbing;
    border-color: var(--accent);
  }
  .knob:focus-visible {
    outline: 2px solid var(--info);
  }
  .disabled .knob {
    opacity: 0.45;
    cursor: not-allowed;
  }
  .disabled .knob::after {
    background: var(--muted);
  }

  /* vertical variant (GEQ) */
  .vertical {
    height: 100%;
    width: 36px;
    padding: 14px 0;
    flex-direction: column;
    justify-content: center;
  }
  .vertical .track {
    width: 6px;
    height: auto;
    flex: 1;
  }
  .vertical .fill {
    top: auto;
    left: 0;
    right: 0;
  }
  .vertical .origin {
    top: auto;
    left: -8px;
    right: -8px;
    width: auto;
    height: 1px;
  }
  .vertical .knob {
    top: auto;
    left: 50%;
    width: 30px;
    height: 22px;
    margin: 0 0 -11px -15px;
    border-radius: 6px;
  }
  .vertical .knob::after {
    inset: 10px 5px;
    border-radius: 1px;
  }
</style>
