<script lang="ts">
  import { onMount } from "svelte";
  import Login from "./components/Login.svelte";
  import Matrix from "./components/Matrix.svelte";
  import Mixer from "./components/Mixer.svelte";
  import Presets from "./components/Presets.svelte";
  import Settings from "./components/Settings.svelte";
  import Toasts from "./components/Toasts.svelte";
  import TopBar from "./components/TopBar.svelte";
  import ChannelDetail from "./components/ChannelDetail.svelte";
  import { app } from "./lib/app.svelte";
  import { nav, TABS } from "./lib/nav.svelte";

  onMount(() => {
    void app.start();
    // Any interaction counts as activity for the lock (throttled in app.activity).
    const onActivity = () => app.activity();
    const onPop = () => nav.fromHash();
    window.addEventListener("popstate", onPop);
    window.addEventListener("pointerdown", onActivity, { passive: true });
    window.addEventListener("keydown", onActivity);
    return () => {
      window.removeEventListener("pointerdown", onActivity);
      window.removeEventListener("keydown", onActivity);
      window.removeEventListener("popstate", onPop);
    };
  });
</script>

{#if app.view === "login"}
  <Login />
{:else if app.view === "app"}
  <div class="layout">
    <TopBar />
    <nav>
      {#each TABS as [key, text, icon] (key)}
        <button
          class:selected={nav.tab === key}
          onclick={() => nav.select(key)}
          aria-current={nav.tab === key}
        >
          <span aria-hidden="true">{icon}</span>{text}
        </button>
      {/each}
    </nav>
    <main>
      {#if !app.device}
        <p class="muted center">
          {app.connected ? "Waiting for the DSP…" : "Connecting to the server…"}
        </p>
      {:else if nav.detail}
        <ChannelDetail path={nav.detail} />
      {:else if nav.tab === "mixer"}
        <Mixer />
      {:else if nav.tab === "matrix"}
        <Matrix />
      {:else if nav.tab === "presets"}
        <Presets />
      {:else}
        <Settings />
      {/if}
    </main>
  </div>
  <Toasts />
{/if}

<style>
  .layout {
    height: 100%;
    display: grid;
    grid-template-rows: auto 1fr auto;
    grid-template-areas: "top" "main" "nav";
  }
  .layout > :global(header) {
    grid-area: top;
  }
  main {
    grid-area: main;
    overflow: auto;
    padding: 12px;
    min-height: 0;
  }
  nav {
    grid-area: nav;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    border-top: 1px solid var(--line);
    background: var(--panel);
    padding-bottom: env(safe-area-inset-bottom);
  }
  nav button {
    border: none;
    border-radius: 0;
    background: none;
    display: grid;
    justify-items: center;
    gap: 2px;
    min-height: 56px;
    font-size: 0.75rem;
    color: var(--muted);
  }
  nav button span {
    font-size: 1.2rem;
  }
  nav button.selected {
    color: var(--accent);
  }
  .center {
    text-align: center;
    margin-top: 20vh;
  }
  @media (min-width: 900px) {
    .layout {
      grid-template-columns: 180px 1fr;
      grid-template-rows: auto 1fr;
      grid-template-areas: "top top" "nav main";
    }
    nav {
      grid-template-columns: none;
      grid-auto-rows: 56px;
      align-content: start;
      border-top: none;
      border-right: 1px solid var(--line);
    }
    nav button {
      grid-auto-flow: column;
      justify-content: start;
      align-items: center;
      gap: 10px;
      padding: 0 18px;
      font-size: 0.95rem;
    }
  }
</style>
