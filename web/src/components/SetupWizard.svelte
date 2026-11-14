<script lang="ts">
  // "Setup" tab: the setup wizard (issue #36). From the sources and the speaker stack to the
  // routing, names, links, crossovers, limiters and gains, written to the live setup and stored
  // in a preset slot. lib/setup.ts does the maths; this component holds the steps together.
  import { app } from "../lib/app.svelte";
  import { filterErrors, inputErrors, planErrors, type Topology } from "../lib/setup";
  import { STEPS, wizard } from "../lib/wizard.svelte";
  import SetupApply from "./SetupApply.svelte";
  import SetupDiagram from "./SetupDiagram.svelte";
  import SetupFilters from "./SetupFilters.svelte";
  import SetupInputs from "./SetupInputs.svelte";
  import SetupPlan from "./SetupPlan.svelte";

  const profile = $derived(app.hello?.profile);
  const topo = $derived<Topology | null>(
    profile
      ? {
          inputs: profile.input_count,
          outputs: profile.output_count,
          presets: profile.preset_count,
          slopes: profile.slopes,
        }
      : null,
  );

  $effect(() => {
    if (topo && !wizard.ready) wizard.start(topo.slopes);
  });

  // What keeps each step from going on (the Apply step checks its own).
  const errors = $derived.by(() => {
    if (!topo) return [];
    const d = wizard.draft;
    return [inputErrors(d, topo), planErrors(d, topo), filterErrors(d, topo)];
  });
  /** The furthest step that can be reached: every step before it is complete. */
  const reachable = $derived.by(() => {
    let step = 0;
    while (step < STEPS.length - 1 && (errors[step]?.length ?? 0) === 0) step++;
    return step;
  });
  const stepErrors = $derived(errors[wizard.step] ?? []);

  function restart() {
    if (!topo) return;
    if (confirm("Start the setup again from scratch? Everything typed in the wizard is lost."))
      wizard.start(topo.slopes);
  }
</script>

{#if topo && wizard.ready}
  <div class="wizard">
    <section class="card head">
      <div class="title">
        <h2>Setup wizard</h2>
        <button class="restart" onclick={restart}>Start again</button>
      </div>
      <ol class="steps" aria-label="Steps">
        {#each STEPS as label, i (label)}
          <li>
            <button
              class:current={wizard.step === i}
              class:done={i < reachable && i !== wizard.step}
              aria-current={wizard.step === i ? "step" : undefined}
              disabled={i > reachable}
              onclick={() => wizard.go(i, topo)}
            >
              <span class="n">{i + 1}</span>
              <span class="label">{label}</span>
            </button>
          </li>
        {/each}
      </ol>
      <p class="muted intro">
        Describe the sources, then draw the system: amplifiers and speakers wired to the DSP's
        outputs. The wizard works out the routing, channel names, links, crossovers, limiters and
        gains, then writes them to the DSP and stores them in a preset. Delays and EQ are left
        flat: set them by ear or by measurement.
      </p>
    </section>

    {#if wizard.step === 1}
      <SetupPlan {topo} />
    {:else}
      <div class="columns">
        <div class="main">
          {#if wizard.step === 0}
            <SetupInputs {topo} />
          {:else if wizard.step === 2}
            <SetupFilters {topo} />
          {:else}
            <SetupApply {topo} />
          {/if}
        </div>
        <aside><SetupDiagram {topo} /></aside>
      </div>
    {/if}

    {#if stepErrors.length}
      <ul class="errors card" aria-live="polite">
        {#each stepErrors as error (error)}<li>{error}</li>{/each}
      </ul>
    {/if}

    <nav class="actions" aria-label="Wizard">
      <button disabled={wizard.step === 0} onclick={() => wizard.go(wizard.step - 1, topo)}
        >← Back</button
      >
      {#if wizard.step < STEPS.length - 1}
        <button
          class="primary"
          disabled={stepErrors.length > 0}
          onclick={() => wizard.go(wizard.step + 1, topo)}
          >Next: {STEPS[wizard.step + 1]} →</button
        >
      {/if}
    </nav>
  </div>
{/if}

<style>
  .wizard {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
  }
  .columns,
  .main {
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    gap: 10px;
    align-content: start;
  }
  /* Wide screens: the diagram on the right, beside the step. */
  @media (min-width: 1000px) {
    .columns {
      grid-template-columns: minmax(0, 1fr) minmax(320px, 420px);
      align-items: start;
    }
    aside {
      position: sticky;
      top: 0;
    }
  }
  .title {
    display: flex;
    justify-content: space-between;
    align-items: start;
    gap: 8px;
  }
  .restart {
    min-height: 36px;
    font-size: 0.85rem;
  }
  .steps {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 4px;
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .steps button {
    width: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0;
    padding: 4px 2px;
    line-height: 1.1;
  }
  .steps .n {
    font-weight: 700;
  }
  .steps .label {
    font-size: 0.75rem;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 100%;
  }
  .steps .done {
    border-color: color-mix(in srgb, var(--accent) 50%, var(--line));
  }
  .steps .current {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--accent-text);
  }
  .intro {
    font-size: 0.85rem;
    margin: 10px 0 0;
  }
  .errors {
    margin: 0;
    padding: 10px 10px 10px 28px;
    border-color: var(--warn);
    color: var(--warn);
    font-size: 0.9rem;
  }
  .actions {
    display: flex;
    justify-content: space-between;
    gap: 8px;
  }
</style>
