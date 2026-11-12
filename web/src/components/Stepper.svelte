<script lang="ts">
  // A setting with a slider between − and + buttons (Settings). `live` calls onchange while the
  // slider moves; otherwise only when it is released (e.g. a value sent to the server).
  interface Props {
    id: string;
    label: string;
    value: number;
    min: number;
    max: number;
    step?: number;
    format?: (value: number) => string;
    disabled?: boolean;
    live?: boolean;
    onchange: (value: number) => void;
  }

  let {
    id,
    label,
    value,
    min,
    max,
    step = 1,
    format = String,
    disabled = false,
    live = false,
    onchange,
  }: Props = $props();

  let draft = $state(0);
  $effect(() => {
    draft = value;
  });

  function set(next: number) {
    const clamped = Math.min(max, Math.max(min, next));
    draft = clamped;
    if (clamped !== value) onchange(clamped);
  }
</script>

<div class="setting">
  <label for={id}>{label}: <strong>{format(draft)}</strong></label>
  <div class="stepper">
    <button disabled={disabled || draft <= min} aria-label={`${label} down`} onclick={() => set(draft - step)}
      >−</button
    >
    <input
      {id}
      type="range"
      {min}
      {max}
      {step}
      value={draft}
      {disabled}
      oninput={(e) => {
        draft = Number(e.currentTarget.value);
        if (live) set(draft);
      }}
      onchange={(e) => set(Number(e.currentTarget.value))}
    />
    <button disabled={disabled || draft >= max} aria-label={`${label} up`} onclick={() => set(draft + step)}
      >+</button
    >
  </div>
</div>

<style>
  .setting {
    display: grid;
    gap: 8px;
    margin: 12px 0 8px;
  }
  /* − slider + */
  .stepper {
    display: grid;
    grid-template-columns: var(--tap) 1fr var(--tap);
    align-items: center;
    gap: 8px;
  }
  .stepper button {
    padding: 0;
    font-size: 1.1rem;
  }
  input {
    width: 100%;
    min-height: var(--tap);
  }
</style>
