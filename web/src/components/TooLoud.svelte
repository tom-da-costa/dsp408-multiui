<script lang="ts">
  // "Too loud" tab: one indicator that fills the screen, for whoever sets the volume. It lights
  // in the compressor's colour when at least one output's compressor or limiter acts (a single
  // colour, so that it does not flash between two), and stays grey otherwise. The outputs
  // concerned are listed with their names. How bright it lights is set at the bottom (from
  // nearly grey to the full colour), remembered in this browser.
  import { app } from "../lib/app.svelte";
  import { slotLabel } from "../lib/nav.svelte";
  import { COMP_COLOR } from "../lib/scale";

  function acting(flags: boolean[] | null | undefined): string[] {
    return (flags ?? []).flatMap((on, i) => {
      if (!on) return [];
      const name = app.device?.outputs[i]?.name;
      return [`${slotLabel(`outputs.${i}`)}${name ? ` (${name})` : ""}`];
    });
  }

  const STORAGE_KEY = "dsp408.loud.brightness";
  const MIN_BRIGHTNESS = 20;

  function loadBrightness(): number {
    try {
      const saved = Number(localStorage.getItem(STORAGE_KEY));
      if (saved >= MIN_BRIGHTNESS && saved <= 100) return saved;
    } catch {
      // storage unavailable: full brightness
    }
    return 100;
  }

  let brightness = $state(loadBrightness());

  function saveBrightness() {
    try {
      localStorage.setItem(STORAGE_KEY, String(brightness));
    } catch {
      // not persisted: fine
    }
  }

  /** The lit colour, mixed with the grey of the unlit panel below full brightness. */
  const litColor = $derived(`color-mix(in srgb, ${COMP_COLOR} ${brightness}%, var(--panel))`);

  const limiting = $derived(acting(app.meters?.limit));
  const compressing = $derived(acting(app.meters?.comp));
  const lit = $derived(limiting.length > 0 || compressing.length > 0);
  // One line for the compressors, one for the limiters.
  const compLine = $derived(
    compressing.length ? `Compressor: ${compressing.join(", ")}` : "No compressor acting",
  );
  const limitLine = $derived(
    limiting.length ? `Limiter: ${limiting.join(", ")}` : "No limiter acting",
  );
</script>

<div class="loud">
  <div
    class="light"
    class:lit
    class:dim={brightness < 60}
    style:--c={litColor}
    style:--glow={`${Math.round((40 * brightness) / 100)}px`}
    role="status"
    aria-live="polite"
    aria-label={lit ? `Too loud. ${compLine}. ${limitLine}.` : "Level fine"}
  >
    <strong>TOO LOUD</strong>
    <span class="detail">{compLine}</span>
    <span class="detail">{limitLine}</span>
  </div>
  <p class="hint">
    Flashing now and then is fine. If it stays lit, turn the volume down.
  </p>
  <label class="brightness">
    <span>Brightness</span>
    <input
      type="range"
      min={MIN_BRIGHTNESS}
      max="100"
      step="5"
      bind:value={brightness}
      onchange={saveBrightness}
      disabled={app.screenLocked}
    />
    <span class="value">{brightness} %</span>
  </label>
</div>

<style>
  .loud {
    height: 100%;
    min-height: 280px;
    display: grid;
    grid-template-rows: 1fr auto auto;
    gap: 12px;
  }
  .light {
    display: grid;
    place-content: center;
    justify-items: center;
    gap: 8px;
    padding: 16px;
    border-radius: var(--radius);
    border: 2px solid var(--line);
    background: var(--panel);
    color: var(--muted);
    text-align: center;
  }
  .light.lit {
    background: var(--c);
    border-color: var(--c);
    color: #000;
    box-shadow: 0 0 var(--glow) var(--c);
  }
  .light.lit.dim {
    color: #fff; /* black would not read on a dim colour */
  }
  strong {
    font-size: clamp(3rem, 14vw, 12rem);
    font-weight: 900;
    line-height: 1;
    letter-spacing: 0.02em;
  }
  .light:not(.lit) strong {
    opacity: 0.35;
  }
  .detail {
    font-size: clamp(1rem, 3vw, 1.6rem);
    font-weight: 700;
  }
  .brightness {
    display: grid;
    grid-template-columns: auto minmax(0, 320px) 6ch;
    justify-content: center;
    align-items: center;
    gap: 10px;
    color: var(--muted);
    font-size: 0.9rem;
  }
  .brightness input {
    width: 100%;
    min-height: var(--tap);
  }
  .brightness .value {
    font-variant-numeric: tabular-nums;
    text-align: right;
    white-space: nowrap;
  }
  .hint {
    margin: 0;
    text-align: center;
    font-size: clamp(1rem, 2.6vw, 1.4rem);
    color: var(--text);
  }
</style>
