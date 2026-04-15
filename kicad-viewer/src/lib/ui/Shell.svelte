<script lang="ts">
  import Tabs from './Tabs.svelte';
  import Footer from './Footer.svelte';
  import SettingsModal from './SettingsModal.svelte';
  import { project } from '$lib/stores/project';
  import { theme, toggleTheme } from '$lib/stores/theme';

  interface Props {
    tab: string;
    onTabChange: (v: string) => void;
    onClear?: () => void;
    onHelp?: () => void;
    children: import('svelte').Snippet;
    sidebar?: import('svelte').Snippet;
    inspector?: import('svelte').Snippet;
    cursorMm?: { x: number; y: number } | null;
  }
  let { tab, onTabChange, onClear, onHelp, children, sidebar, inspector, cursorMm }: Props = $props();

  let settingsOpen = $state(false);

  const LS_KEY = 'kv.shell.sidebars.v1';
  function loadCollapsed(): { left: boolean; right: boolean } {
    if (typeof localStorage === 'undefined') return { left: false, right: false };
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (!raw) return { left: false, right: false };
      const parsed = JSON.parse(raw);
      return { left: !!parsed.left, right: !!parsed.right };
    } catch {
      return { left: false, right: false };
    }
  }
  const initial = loadCollapsed();
  let leftCollapsed = $state(initial.left);
  let rightCollapsed = $state(initial.right);

  $effect(() => {
    if (typeof localStorage === 'undefined') return;
    try {
      localStorage.setItem(LS_KEY, JSON.stringify({ left: leftCollapsed, right: rightCollapsed }));
    } catch {
      // ignore
    }
  });

  const gridCols = $derived(
    `${leftCollapsed ? '28px' : '220px'} 1fr ${rightCollapsed ? '28px' : '280px'}`
  );
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
      <button onclick={() => (settingsOpen = true)} class="iconbtn" aria-label="Settings">Settings</button>
      {#if onHelp}
        <button onclick={onHelp} class="iconbtn" aria-label="Keyboard shortcuts">?</button>
      {/if}
      <button onclick={toggleTheme} class="iconbtn" aria-label="Toggle theme">{$theme === 'dark' ? '☾' : '☀'}</button>
    </div>
  </header>

  <div class="body" style="grid-template-columns: {gridCols};">
    <aside class="side left" class:collapsed={leftCollapsed}>
      <div class="side-header">
        {#if !leftCollapsed}
          <span class="side-title">Project</span>
        {/if}
        <button
          class="collapse-btn"
          onclick={() => (leftCollapsed = !leftCollapsed)}
          aria-label={leftCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          title={leftCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        >{leftCollapsed ? '›' : '‹'}</button>
      </div>
      {#if !leftCollapsed}
        <div class="side-body">{@render sidebar?.()}</div>
      {/if}
    </aside>
    <main class="main">{@render children()}</main>
    <aside class="side right" class:collapsed={rightCollapsed}>
      <div class="side-header">
        <button
          class="collapse-btn"
          onclick={() => (rightCollapsed = !rightCollapsed)}
          aria-label={rightCollapsed ? 'Expand inspector' : 'Collapse inspector'}
          title={rightCollapsed ? 'Expand inspector' : 'Collapse inspector'}
        >{rightCollapsed ? '‹' : '›'}</button>
        {#if !rightCollapsed}
          <span class="side-title">Inspector</span>
        {/if}
      </div>
      {#if !rightCollapsed}
        <div class="side-body">{@render inspector?.()}</div>
      {/if}
    </aside>
  </div>

  <Footer projectName={$project?.name ?? ''} cursorMm={cursorMm ?? null} />
</div>

<SettingsModal open={settingsOpen} onClose={() => (settingsOpen = false)} />

<style>
  /* Definite height (not min-height) so the 1fr body row has a resolved size;
     otherwise tall sidebar content grows the shell past the viewport and the
     PCB canvas host stretches with it. */
  .shell { display: grid; grid-template-rows: auto 1fr auto; height: 100dvh; overflow: hidden; }
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
    min-height: 0;
  }
  /* min-height/min-width: 0 stops grid children from expanding to their
     intrinsic content size, which was stretching the PCB canvas host to
     thousands of pixels when the nets/layers panels had long lists. */
  .side {
    background: var(--kv-surface); border-right: 1px solid var(--kv-border);
    min-height: 0; min-width: 0;
    display: flex; flex-direction: column;
  }
  .side.right { border-right: none; border-left: 1px solid var(--kv-border); }
  .side-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 4px 6px; border-bottom: 1px solid var(--kv-border);
    flex: 0 0 auto;
  }
  .side.collapsed .side-header { justify-content: center; padding: 4px 2px; }
  .side-title {
    font-size: 0.75rem; font-weight: 600;
    color: var(--kv-text-dim); text-transform: uppercase; letter-spacing: 0.05em;
  }
  .collapse-btn {
    background: transparent; border: 1px solid var(--kv-border); border-radius: 4px;
    color: var(--kv-text); cursor: pointer;
    width: 20px; height: 20px; padding: 0; line-height: 1;
    display: inline-flex; align-items: center; justify-content: center;
    font-size: 0.9rem;
  }
  .collapse-btn:hover { background: var(--kv-surface-2); }
  .side-body { flex: 1 1 auto; overflow: auto; min-height: 0; }
  .main {
    overflow: hidden; background: var(--kv-render-bg);
    min-height: 0; min-width: 0;
  }
</style>
