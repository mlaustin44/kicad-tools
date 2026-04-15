<script lang="ts">
  import Tabs from './Tabs.svelte';
  import Footer from './Footer.svelte';
  import { project } from '$lib/stores/project';
  import { theme, toggleTheme } from '$lib/stores/theme';

  interface Props {
    tab: string;
    onTabChange: (v: string) => void;
    onClear?: () => void;
    children: import('svelte').Snippet;
    sidebar?: import('svelte').Snippet;
    inspector?: import('svelte').Snippet;
    cursorMm?: { x: number; y: number } | null;
  }
  let { tab, onTabChange, onClear, children, sidebar, inspector, cursorMm }: Props = $props();
</script>

<div class="shell">
  <header class="top">
    <strong>kicad-viewer</strong>
    <span class="project">{$project?.name ?? ''}</span>
    <Tabs value={tab} onChange={onTabChange} />
    <div class="actions">
      {#if onClear}
        <button onclick={onClear} class="iconbtn" aria-label="Clear project">Clear</button>
      {/if}
      <button onclick={toggleTheme} class="iconbtn" aria-label="Toggle theme">{$theme === 'dark' ? '☾' : '☀'}</button>
    </div>
  </header>

  <div class="body">
    <aside class="side left">{@render sidebar?.()}</aside>
    <main class="main">{@render children()}</main>
    <aside class="side right">{@render inspector?.()}</aside>
  </div>

  <Footer projectName={$project?.name ?? ''} cursorMm={cursorMm ?? null} />
</div>

<style>
  .shell { display: grid; grid-template-rows: auto 1fr auto; min-height: 100dvh; }
  .top {
    display: grid; grid-template-columns: auto auto 1fr auto;
    align-items: center; gap: 1rem;
    padding: 0.4rem 1rem; border-bottom: 1px solid var(--kv-border);
    background: var(--kv-surface);
  }
  .project { color: var(--kv-text-dim); font-size: 0.85rem; }
  .actions { display: flex; gap: 0.4rem; }
  .actions .iconbtn { background: transparent; border: 1px solid var(--kv-border); border-radius: 6px; padding: 4px 8px; color: var(--kv-text); cursor: pointer; }
  .actions .iconbtn:hover { background: var(--kv-surface-2); }
  .body {
    display: grid;
    grid-template-columns: 220px 1fr 280px;
    min-height: 0;
  }
  .side { background: var(--kv-surface); border-right: 1px solid var(--kv-border); overflow: auto; }
  .side.right { border-right: none; border-left: 1px solid var(--kv-border); }
  .main { overflow: hidden; background: var(--kv-render-bg); }
</style>
