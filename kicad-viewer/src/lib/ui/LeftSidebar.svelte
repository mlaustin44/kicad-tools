<script lang="ts">
  import SheetTree from './SheetTree.svelte';
  import LayerPanel from './LayerPanel.svelte';
  import NetsPanel from './NetsPanel.svelte';
  import ComponentsPanel from './ComponentsPanel.svelte';
  import { leftSidebarTab } from '$lib/stores/leftSidebar';

  interface Props {
    view: 'sch' | 'pcb' | '3d';
    activeSheet: string | null;
    onSelectSheet: (uuid: string) => void;
  }
  let { view, activeSheet, onSelectSheet }: Props = $props();

  const firstLabel = $derived(view === 'sch' ? 'Pages' : 'Layers');
  const showFirstTab = $derived(view !== '3d');

  // Auto-switch away from Layers tab when it's hidden in 3D view
  $effect(() => {
    if (!showFirstTab && $leftSidebarTab === 0) {
      leftSidebarTab.set(1);
    }
  });
</script>

<div class="wrap">
  <div class="tabs" class:two-tabs={!showFirstTab} role="tablist">
    {#if showFirstTab}
      <button
        role="tab"
        aria-selected={$leftSidebarTab === 0}
        class:active={$leftSidebarTab === 0}
        onclick={() => leftSidebarTab.set(0)}
      >{firstLabel}</button>
    {/if}
    <button
      role="tab"
      aria-selected={$leftSidebarTab === 1}
      class:active={$leftSidebarTab === 1}
      onclick={() => leftSidebarTab.set(1)}
    >Nets</button>
    <button
      role="tab"
      aria-selected={$leftSidebarTab === 2}
      class:active={$leftSidebarTab === 2}
      onclick={() => leftSidebarTab.set(2)}
    >Components</button>
  </div>
  <div class="pane">
    {#if $leftSidebarTab === 0 && view === 'sch'}
      <div class="scroll"><SheetTree activeUuid={activeSheet} onSelect={onSelectSheet} /></div>
    {:else if $leftSidebarTab === 0 && view === 'pcb'}
      <div class="scroll"><LayerPanel /></div>
    {:else if $leftSidebarTab === 1}
      <NetsPanel />
    {:else}
      <ComponentsPanel />
    {/if}
  </div>
</div>

<style>
  .wrap {
    display: grid; grid-template-rows: auto 1fr;
    height: 100%; min-height: 0;
  }
  .tabs {
    display: grid; grid-template-columns: 1fr 1fr 1fr;
    border-bottom: 1px solid var(--kv-border);
  }
  .tabs.two-tabs {
    grid-template-columns: 1fr 1fr;
  }
  .tabs button {
    background: transparent; border: none; color: var(--kv-text-dim);
    padding: 6px 4px;
    font-size: 0.7rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.05em;
    cursor: pointer;
    border-bottom: 2px solid transparent;
  }
  .tabs button:hover { background: var(--kv-surface-2); }
  .tabs button.active {
    color: var(--kv-accent, #6aa6ff);
    border-bottom-color: var(--kv-accent, #6aa6ff);
  }
  .pane { min-height: 0; display: flex; flex-direction: column; }
  .pane > :global(*) { flex: 1 1 auto; min-height: 0; }
  .scroll { overflow: auto; min-height: 0; }
</style>
