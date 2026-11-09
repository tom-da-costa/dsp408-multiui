<script lang="ts">
  import {
    dbToPos,
    formatDb,
    GAIN_MAX,
    GAIN_MIN,
    gainStep,
    posToDb,
    quantizeGain,
  } from "../lib/scale";
  import { holdRepeat } from "../lib/repeat";
  import { throttleLatest } from "../lib/throttle";

  interface Props {
    value: number;
    disabled?: boolean;
    label: string;
    onchange: (db: number) => void;
  }

  let { value, disabled = false, label, onchange }: Props = $props();

  let track: HTMLDivElement | undefined = $state();
  let dragging = $state(false);
  let local = $state(0);
  let editing = $state(false);
  let draft = $state("");

  // While dragging, show the local value; after − / +, the value sent until the DSP has it;
  // otherwise follow the server.
  let pending = $state<number | null>(null);
  let settle: ReturnType<typeof setTimeout> | undefined;
  const shown = $derived(dragging ? local : (pending ?? value));
  $effect(() => {
    if (pending !== null && Math.abs(value - pending) < 0.05) pending = null;
  });
  const sender = throttleLatest((db: number) => onchange(db), 50);

  function fromPointer(clientY: number): number {
    if (!track) return value;
    const rect = track.getBoundingClientRect();
    return quantizeGain(posToDb(1 - (clientY - rect.top) / rect.height));
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
    const db = fromPointer(event.clientY);
    if (db !== local) {
      local = db;
      sender.push(db);
    }
  }

  function up() {
    if (!dragging) return;
    sender.flush();
    dragging = false;
  }

  /** Move by `count` device steps (0.1 dB, or 0.5 dB below -20 dB), chaining from the last
   * value sent so that a held button does not wait for the DSP's answer. */
  function nudge(count: number) {
    if (disabled) return;
    const from = pending ?? value;
    let db = from;
    for (let i = 0; i < Math.abs(count); i++) db = gainStep(db, count > 0 ? 1 : -1);
    if (db === from) return;
    pending = db;
    clearTimeout(settle);
    settle = setTimeout(() => (pending = null), 1500);
    onchange(db);
  }

  function key(event: KeyboardEvent) {
    const steps: Record<string, number> = { ArrowUp: 1, ArrowDown: -1, PageUp: 10, PageDown: -10 };
    const step = steps[event.key];
    if (step !== undefined) {
      event.preventDefault();
      nudge(step);
    }
  }

  function startEdit() {
    if (disabled) return;
    draft = shown.toFixed(1);
    editing = true;
  }

  function commitEdit(event: SubmitEvent) {
    event.preventDefault();
    const db = Number(draft.replace(",", "."));
    if (Number.isFinite(db)) onchange(quantizeGain(Math.min(GAIN_MAX, Math.max(GAIN_MIN, db))));
    editing = false;
  }
</script>

<div class="fader" class:disabled>
  {#if editing}
    <form onsubmit={commitEdit}>
      <!-- svelte-ignore a11y_autofocus -->
      <input
        type="text"
        inputmode="decimal"
        bind:value={draft}
        onblur={() => (editing = false)}
        onfocus={(e) => e.currentTarget.select()}
        autofocus
        aria-label={`${label} gain in dB`}
      />
    </form>
  {:else}
    <button class="value" onclick={startEdit} {disabled} aria-label={`${label} gain, tap to type`}>
      {formatDb(shown)}
    </button>
  {/if}
  <button
    class="step"
    use:holdRepeat={{ step: (n) => nudge(n), disabled }}
    {disabled}
    aria-label="gain up (hold to repeat)">+</button
  >
  <div class="track" bind:this={track}>
    <div class="unity" style:bottom={`${dbToPos(0) * 100}%`}></div>
    <div
      class="knob"
      class:active={dragging}
      style:bottom={`calc(${dbToPos(shown) * 100}% - 14px)`}
      role="slider"
      tabindex={disabled ? -1 : 0}
      aria-label={`${label} gain`}
      aria-valuemin={GAIN_MIN}
      aria-valuemax={GAIN_MAX}
      aria-valuenow={shown}
      aria-disabled={disabled}
      onpointerdown={down}
      onpointermove={move}
      onpointerup={up}
      onpointercancel={up}
      onkeydown={key}
    ></div>
  </div>
  <button
    class="step"
    use:holdRepeat={{ step: (n) => nudge(-n), disabled }}
    {disabled}
    aria-label="gain down (hold to repeat)">−</button
  >
</div>

<style>
  .fader {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    height: 100%;
  }
  .value {
    min-height: 32px;
    width: 54px;
    padding: 0;
    font-variant-numeric: tabular-nums;
    font-size: 0.85rem;
  }
  form input {
    width: 54px;
    min-height: 32px;
    text-align: center;
    padding: 0 4px;
  }
  .step {
    min-height: 32px;
    width: 40px;
    padding: 0;
  }
  .track {
    position: relative;
    flex: 1;
    width: 6px;
    min-height: 120px;
    border-radius: 3px;
    background: #0b0c0f;
    margin: 14px 0;
  }
  .unity {
    position: absolute;
    left: -8px;
    right: -8px;
    height: 1px;
    background: var(--muted);
  }
  .knob {
    position: absolute;
    left: 50%;
    width: 36px;
    height: 28px;
    margin-left: -18px;
    border-radius: 6px;
    background: linear-gradient(#4a505c, #2d323b);
    border: 1px solid #5d6573;
    box-shadow: inset 0 -2px 0 rgba(0, 0, 0, 0.35);
    touch-action: none;
    cursor: grab;
  }
  .knob::after {
    content: "";
    position: absolute;
    left: 6px;
    right: 6px;
    top: 13px;
    height: 2px;
    background: var(--accent);
  }
  .knob.active {
    cursor: grabbing;
    border-color: var(--accent);
  }
  .disabled .knob {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
