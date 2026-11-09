<script lang="ts">
  import { onMount } from "svelte";
  import AllInOne from "./components/AllInOne.svelte";
  import ChannelsView from "./components/ChannelsView.svelte";
  import Login from "./components/Login.svelte";
  import ParamView from "./components/ParamView.svelte";
  import Presets from "./components/Presets.svelte";
  import Settings from "./components/Settings.svelte";
  import Toasts from "./components/Toasts.svelte";
  import TopBar from "./components/TopBar.svelte";
  import { app } from "./lib/app.svelte";
  import { nav, TABS, type Tab } from "./lib/nav.svelte";

  // The tab rail is always on the left; expanded it shows the labels (remembered per browser).
  const RAIL_KEY = "dsp408.rail.expanded";
  let expanded = $state(readExpanded());

  function readExpanded(): boolean {
    try {
      return localStorage.getItem(RAIL_KEY) === "1";
    } catch {
      return false;
    }
  }

  function toggleRail() {
    expanded = !expanded;
    try {
      localStorage.setItem(RAIL_KEY, expanded ? "1" : "0");
    } catch {
      // not persisted: fine
    }
  }

  function select(tab: Tab) {
    nav.select(tab);
    // On a phone the expanded rail covers the page: fold it once a tab is picked.
    if (expanded && window.matchMedia("(max-width: 699px)").matches) toggleRail();
  }

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
  <div class="layout" class:expanded>
    <nav aria-label="Views">
      <button
        class="fold"
        onclick={toggleRail}
        aria-expanded={expanded}
        aria-label={expanded ? "Collapse the tab bar" : "Expand the tab bar"}
        title={expanded ? "Collapse" : "Expand"}
      >
        <span class="icon" aria-hidden="true">{expanded ? "«" : "»"}</span>
      </button>
      {#each TABS as [key, text, icon] (key)}
        <button
          class:selected={nav.tab === key}
          onclick={() => select(key)}
          aria-current={nav.tab === key}
          title={text}
        >
          <span class="icon" aria-hidden="true">{icon}</span>
          <span class="text">{text}</span>
        </button>
      {/each}
    </nav>
    {#if expanded}
      <button class="scrim" aria-label="Collapse the tab bar" onclick={toggleRail}></button>
    {/if}
    <div class="page">
      <TopBar />
      <main>
        {#if !app.device}
          <p class="muted center">
            {app.connected ? "Waiting for the DSP…" : "Connecting to the server…"}
          </p>
        {:else if nav.tab === "params"}
          <ParamView />
        {:else if nav.tab === "channels"}
          <ChannelsView />
        {:else if nav.tab === "aio"}
          <AllInOne />
        {:else if nav.tab === "presets"}
          <Presets />
        {:else}
          <Settings />
        {/if}
      </main>
    </div>
  </div>
  <Toasts />
{/if}

<style>
  .layout {
    --rail: 56px;
    --rail-open: 180px;
    position: relative;
    height: 100%;
    display: grid;
    grid-template-columns: var(--rail) 1fr;
  }
  nav {
    position: relative;
    z-index: 5;
    width: var(--rail);
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 6px 0 env(safe-area-inset-bottom);
    background: var(--panel);
    border-right: 1px solid var(--line);
    overflow: hidden auto;
    transition: width 0.15s ease;
  }
  nav button {
    display: flex;
    align-items: center;
    gap: 12px;
    min-height: 52px;
    margin: 0 6px;
    padding: 0 10px;
    border: none;
    border-radius: 8px;
    background: none;
    color: var(--muted);
    white-space: nowrap;
    text-align: left;
  }
  nav .icon {
    flex: 0 0 24px;
    font-size: 1.25rem;
    text-align: center;
  }
  nav .text {
    font-size: 0.95rem;
    opacity: 0;
    transition: opacity 0.1s;
  }
  nav button.selected {
    color: var(--accent);
    background: var(--panel-2);
  }
  nav .fold {
    min-height: 44px;
    margin-bottom: 6px;
  }
  .expanded nav {
    width: var(--rail-open);
  }
  .expanded nav .text {
    opacity: 1;
  }
  .scrim {
    display: none;
  }
  .page {
    grid-column: 2; /* stays put when the expanded rail floats (phone) */
    min-width: 0;
    display: grid;
    grid-template-rows: auto 1fr;
    min-height: 0;
  }
  main {
    overflow: auto;
    padding: 12px;
    min-height: 0;
  }
  .center {
    text-align: center;
    margin-top: 20vh;
  }
  /* Phone: the expanded rail floats over the page instead of squeezing it. */
  @media (max-width: 699px) {
    .expanded nav {
      position: absolute;
      top: 0;
      bottom: 0;
      left: 0;
      box-shadow: 4px 0 16px #0008;
    }
    .expanded .scrim {
      display: block;
      position: absolute;
      inset: 0;
      z-index: 4;
      min-height: 0;
      border: none;
      border-radius: 0;
      background: #0006;
    }
  }
  /* Wider screens: the expanded rail pushes the page. */
  @media (min-width: 700px) {
    .expanded {
      grid-template-columns: var(--rail-open) 1fr;
    }
  }
</style>
