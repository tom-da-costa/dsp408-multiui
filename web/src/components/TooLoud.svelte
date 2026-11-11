<script lang="ts">
  // "Too loud" tab: one indicator that fills the screen, for whoever sets the volume. It takes
  // the limiter's colour when at least one output's limiter acts, else the compressor's when at
  // least one output's compressor acts (the limiter prevails), and is green otherwise.
  import { app } from "../lib/app.svelte";
  import { slotLabel } from "../lib/nav.svelte";
  import { COMP_COLOR, LIMIT_COLOR, METER_COLORS } from "../lib/scale";

  const limiting = $derived(
    (app.meters?.limit ?? []).flatMap((on, i) => (on ? [slotLabel(`outputs.${i}`)] : [])),
  );
  const compressing = $derived(
    (app.meters?.comp ?? []).flatMap((on, i) => (on ? [slotLabel(`outputs.${i}`)] : [])),
  );
  const state = $derived(limiting.length ? "limit" : compressing.length ? "comp" : "ok");
  const color = $derived(
    state === "limit" ? LIMIT_COLOR : state === "comp" ? COMP_COLOR : METER_COLORS.green,
  );
  const detail = $derived(
    state === "limit"
      ? `Limiter: ${limiting.join(", ")}`
      : state === "comp"
        ? `Compressor: ${compressing.join(", ")}`
        : "No compressor or limiter acting",
  );
</script>

<div class="loud">
  <div
    class="light"
    class:lit={state !== "ok"}
    style:--c={color}
    role="status"
    aria-live="polite"
    aria-label={state === "ok" ? "Level fine" : `Too loud: ${detail}`}
  >
    <strong>TOO LOUD</strong>
    <span class="detail">{detail}</span>
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
    border: 2px solid var(--c);
    background: var(--c);
    color: #000;
    text-align: center;
  }
  .light.lit {
    box-shadow: 0 0 40px var(--c);
  }
  strong {
    font-size: clamp(3rem, 14vw, 12rem);
    font-weight: 900;
    line-height: 1;
    letter-spacing: 0.02em;
  }
  .detail {
    font-size: clamp(1rem, 3vw, 1.6rem);
    font-weight: 700;
  }
  /* All fine (green): white text, the warning faded like an unlit sign. */
  .light:not(.lit) {
    color: #fff;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.25);
  }
  .light:not(.lit) strong {
    opacity: 0.45;
  }
  .hint {
    margin: 0;
    text-align: center;
    font-size: clamp(1rem, 2.6vw, 1.4rem);
    color: var(--text);
  }
</style>
