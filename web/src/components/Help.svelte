<script lang="ts">
  // "Help" tab: how to use the app (tabs, buttons, control, presets, settings) and what the
  // audio settings do, in English or French (only this page is translated: the rest of the UI is
  // in English). The language follows the browser's until one is picked, then it is remembered
  // here. The contents jump to a section by scrolling (the URL hash is the app's navigation, so
  // no #anchors).
  import HelpEn from "./HelpEn.svelte";
  import HelpFr from "./HelpFr.svelte";

  type Lang = "en" | "fr";
  const STORAGE_KEY = "dsp408.help.lang";

  function loadLang(): Lang {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === "en" || saved === "fr") return saved;
    } catch {
      // storage unavailable: the browser's language
    }
    return navigator.language.toLowerCase().startsWith("fr") ? "fr" : "en";
  }

  let lang = $state<Lang>(loadLang());

  function pick(next: Lang) {
    lang = next;
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // not persisted: fine
    }
  }

  const SECTIONS: Record<Lang, [string, string][]> = {
    en: [
      ["start", "Getting started"],
      ["rail", "The side bar"],
      ["tabs", "The tabs"],
      ["channels", "Choosing the channels shown"],
      ["controls", "Faders, fields and buttons"],
      ["together", "Several people at once"],
      ["presets", "Presets"],
      ["settings", "Settings"],
      ["audio", "Audio settings explained"],
      ["safety", "Good habits"],
    ],
    fr: [
      ["start", "Prise en main"],
      ["rail", "La barre latérale"],
      ["tabs", "Les onglets"],
      ["channels", "Choisir les voies affichées"],
      ["controls", "Faders, champs et boutons"],
      ["together", "À plusieurs en même temps"],
      ["presets", "Presets"],
      ["settings", "Réglages"],
      ["audio", "Les réglages audio expliqués"],
      ["safety", "Bonnes habitudes"],
    ],
  };

  function go(id: string) {
    document.getElementById(`help-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
</script>

<article class="help" lang={lang}>
  <div class="top">
    <h1>{lang === "fr" ? "Aide" : "Help"}</h1>
    <div class="lang" role="group" aria-label="Language">
      <button class:on={lang === "en"} aria-pressed={lang === "en"} onclick={() => pick("en")}
        >EN</button
      >
      <button class:on={lang === "fr"} aria-pressed={lang === "fr"} onclick={() => pick("fr")}
        >FR</button
      >
    </div>
  </div>
  <nav class="toc" aria-label={lang === "fr" ? "Sommaire" : "Contents"}>
    {#each SECTIONS[lang] as [id, title] (id)}
      <button onclick={() => go(id)}>{title}</button>
    {/each}
  </nav>
  {#if lang === "fr"}<HelpFr />{:else}<HelpEn />{/if}
</article>

<style>
  .help {
    max-width: 860px;
    margin: 0 auto;
    line-height: 1.5;
  }
  .top {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 10px;
  }
  h1 {
    margin: 0;
    font-size: 1.5rem;
  }
  .lang {
    display: flex;
    gap: 4px;
  }
  .lang button {
    min-height: 36px;
    min-width: 48px;
    font-weight: 700;
  }
  .lang button.on {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--accent-text);
  }
  .toc {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 16px;
  }
  .toc button {
    min-height: 36px;
    border-radius: 18px;
    font-size: 0.85rem;
  }
  .help :global(section) {
    margin-bottom: 14px;
    padding: 12px 16px;
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: var(--radius);
    scroll-margin-top: 8px;
  }
  .help :global(h2) {
    margin: 0 0 8px;
    font-size: 1.15rem;
  }
  .help :global(p),
  .help :global(ul) {
    margin: 0 0 8px;
  }
  .help :global(ul) {
    padding-left: 20px;
  }
  .help :global(li) {
    margin-bottom: 4px;
  }
  .help :global(dl) {
    margin: 0;
    display: grid;
    gap: 2px 16px;
    grid-template-columns: minmax(0, 12rem) minmax(0, 1fr);
  }
  .help :global(dt) {
    font-weight: 700;
    padding-top: 6px;
  }
  .help :global(dd) {
    margin: 0;
    padding-top: 6px;
    color: var(--text);
  }
  @media (max-width: 600px) {
    .help :global(dl) {
      grid-template-columns: 1fr;
    }
    .help :global(dd) {
      padding-top: 0;
      margin-bottom: 6px;
    }
  }
  .help :global(code) {
    font-size: 0.85em;
  }
</style>
