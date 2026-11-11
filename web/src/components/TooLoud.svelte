<script lang="ts">
  // "Too loud" tab: one indicator that fills the screen, for whoever sets the volume. It lights
  // in the compressor's colour when at least one output's compressor or limiter acts (a single
  // colour, so that it does not flash between two), and stays grey otherwise. The outputs
  // concerned are listed with their names.
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
    style:--c={COMP_COLOR}
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
</div>

<style>
  .loud {
    height: 100%;
    min-height: 280px;
    display: grid;
    grid-template-rows: 1fr auto;
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
    box-shadow: 0 0 40px var(--c);
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
  .hint {
    margin: 0;
    text-align: center;
    font-size: clamp(1rem, 2.6vw, 1.4rem);
    color: var(--text);
  }
</style>
