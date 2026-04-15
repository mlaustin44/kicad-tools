<script lang="ts">
  import { onMount } from 'svelte';
  import type { Component } from 'svelte';
  import { get } from 'svelte/store';
  import { installKeyboardShortcuts } from '$lib/keys';
  import Shell from '$lib/ui/Shell.svelte';
  import HelpOverlay from '$lib/ui/HelpOverlay.svelte';
  import DropZone from '$lib/ui/DropZone.svelte';
  import Toast from '$lib/ui/Toast.svelte';
  import Inspector from '$lib/ui/Inspector.svelte';
  import SchematicView from '$lib/views/SchematicView.svelte';
  import PcbView from '$lib/views/PcbView.svelte';
  import SheetTree from '$lib/ui/SheetTree.svelte';
  import LayerPanel from '$lib/ui/LayerPanel.svelte';
  import NetsPanel from '$lib/ui/NetsPanel.svelte';
  import ComponentsPanel from '$lib/ui/ComponentsPanel.svelte';
  import SearchBar from '$lib/ui/SearchBar.svelte';
  import SplitPane from '$lib/ui/SplitPane.svelte';
  import { project, componentsByUuid, setProjectRevokingGlb } from '$lib/stores/project';
  import { selection } from '$lib/stores/selection';
  import { loadRecent, clearRecent } from '$lib/stores/recent';
  import { classifyFiles, rootSchematic } from '$lib/loader/blob';
  import { toProject } from '$lib/adapter/adapter';

  let tab = $state('sch');
  let searchOpen = $state(false);
  let helpOpen = $state(false);
  let fitRequested = $state(0);
  let panPulse = $state({ dx: 0, dy: 0, seq: 0 });
  let presetRequested = $state<'top' | 'bottom' | 'iso' | null>(null);
  let activeSheet = $state<string | null>(null);
  let cursorMm = $state<{ x: number; y: number } | null>(null);
  let leftPane = $state<'sch' | 'pcb' | '3d'>('sch');
  let rightPane = $state<'sch' | 'pcb' | '3d'>('pcb');

  let ThreeDViewAsync = $state<Component | null>(null);

  async function loadThreeD(): Promise<void> {
    if (ThreeDViewAsync) return;
    const mod = await import('$lib/views/ThreeDView.svelte');
    ThreeDViewAsync = mod.default as unknown as Component;
  }

  $effect(() => {
    if (tab === '3d' || (tab === 'split' && (leftPane === '3d' || rightPane === '3d'))) {
      void loadThreeD();
    }
  });

  $effect(() => {
    const p = $project;
    if (!p) { activeSheet = null; return; }
    if (!activeSheet || !p.sheets.some((s) => s.uuid === activeSheet)) {
      activeSheet = p.sheets[0]?.uuid ?? null;
    }
  });

  $effect(() => {
    const s = $selection;
    if (!s || s.kind !== 'component' || s.source === 'sch') return;
    const c = $componentsByUuid.get(s.uuid);
    if (!c) return;
    if (activeSheet !== c.sheetUuid) activeSheet = c.sheetUuid;
    if (tab !== 'sch' && tab !== 'split') tab = 'sch';
  });

  onMount(() => {
    const teardown = installKeyboardShortcuts({
      setTab: (t) => (tab = t),
      onSearch: () => (searchOpen = true),
      onFit: () => fitRequested++,
      onPan: (dx, dy) => { panPulse = { dx, dy, seq: panPulse.seq + 1 }; },
      onPrevSheet: () => {
        const p = get(project);
        if (!p || !activeSheet) return;
        const idx = p.sheets.findIndex((s) => s.uuid === activeSheet);
        if (idx > 0) activeSheet = p.sheets[idx - 1]!.uuid;
      },
      onNextSheet: () => {
        const p = get(project);
        if (!p || !activeSheet) return;
        const idx = p.sheets.findIndex((s) => s.uuid === activeSheet);
        if (idx >= 0 && idx + 1 < p.sheets.length) {
          activeSheet = p.sheets[idx + 1]!.uuid;
        }
      },
      onFocusLayers: () => {
        if (tab !== 'pcb' && tab !== 'split') tab = 'pcb';
        queueMicrotask(() => {
          const panel = document.getElementById('layer-panel');
          panel?.querySelector<HTMLInputElement>('input[type="checkbox"]')?.focus();
        });
      },
      onPreset: (preset) => {
        // Clear-then-set so the effect re-fires when the same key is pressed twice.
        presetRequested = null;
        queueMicrotask(() => (presetRequested = preset));
      },
      onHelp: () => (helpOpen = !helpOpen)
    });

    hydrateFromIdb();

    return teardown;
  });

  async function hydrateFromIdb(): Promise<void> {
    if (get(project)) return;
    const files = await loadRecent();
    if (!files) return;
    if (get(project)) return;
    const blob = classifyFiles(files);
    const root = rootSchematic(blob);
    if (!blob.kicadPcb || !root) return;
    const schematics: Record<string, string> = {};
    for (const s of blob.schematics) schematics[s] = blob.files[s] as string;
    const p = toProject({
      pro: blob.kicadPro ? (blob.files[blob.kicadPro] as string) : '{}',
      pcb: blob.files[blob.kicadPcb] as string,
      schematics,
      rootSchematic: root
    });
    if (blob.glb) {
      const u8 = blob.files[blob.glb] as Uint8Array;
      p.glbUrl = URL.createObjectURL(new Blob([u8 as BlobPart], { type: 'model/gltf-binary' }));
    }
    if (blob.manifest) p.source = 'bundle';
    setProjectRevokingGlb(p);
  }

  async function clearProject(): Promise<void> {
    setProjectRevokingGlb(null);
    await clearRecent();
  }
</script>

<svelte:head><title>Viewer — kicad-viewer</title></svelte:head>

{#if $project}
  <Shell {tab} onTabChange={(v) => (tab = v)} {cursorMm} onClear={clearProject} onHelp={() => (helpOpen = true)}>
    {#snippet sidebar()}
      {#if tab === 'sch'}
        <SheetTree activeUuid={activeSheet} onSelect={(u) => (activeSheet = u)} />
      {:else if tab === 'pcb'}
        <div class="pcb-sidebar">
          <LayerPanel />
          <NetsPanel />
        </div>
      {:else if tab === '3d'}
        <ComponentsPanel />
      {:else}
        <div class="panel">({tab} sidebar)</div>
      {/if}
    {/snippet}
    {#snippet inspector()}<Inspector />{/snippet}
    {#if tab === 'sch'}
      <SchematicView activeSheetUuid={activeSheet} onNavigateSheet={(u) => (activeSheet = u)} {fitRequested} {panPulse} />
    {:else if tab === 'pcb'}
      <PcbView onCursor={(c) => (cursorMm = c)} {fitRequested} {panPulse} />
    {:else if tab === '3d'}
      {#if ThreeDViewAsync}
        {@const View = ThreeDViewAsync}
        <View {fitRequested} {presetRequested} />
      {:else}
        <div class="stage-loading">Loading 3D view…</div>
      {/if}
    {:else if tab === 'split'}
      <SplitPane>
        {#snippet left()}
          <div class="pane-with-picker">
            <select bind:value={leftPane}>
              <option value="sch">Schematic</option>
              <option value="pcb">PCB</option>
              <option value="3d">3D</option>
            </select>
            {#if leftPane === 'sch'}
              <SchematicView activeSheetUuid={activeSheet} onNavigateSheet={(u) => (activeSheet = u)} {fitRequested} {panPulse} />
            {:else if leftPane === 'pcb'}
              <PcbView onCursor={(c) => (cursorMm = c)} {fitRequested} {panPulse} />
            {:else if ThreeDViewAsync}
              {@const View = ThreeDViewAsync}
              <View {fitRequested} {presetRequested} />
            {:else}
              <div class="stage-loading">Loading 3D view…</div>
            {/if}
          </div>
        {/snippet}
        {#snippet right()}
          <div class="pane-with-picker">
            <select bind:value={rightPane}>
              <option value="sch">Schematic</option>
              <option value="pcb">PCB</option>
              <option value="3d">3D</option>
            </select>
            {#if rightPane === 'sch'}
              <SchematicView activeSheetUuid={activeSheet} onNavigateSheet={(u) => (activeSheet = u)} {fitRequested} {panPulse} />
            {:else if rightPane === 'pcb'}
              <PcbView onCursor={(c) => (cursorMm = c)} {fitRequested} {panPulse} />
            {:else if ThreeDViewAsync}
              {@const View = ThreeDViewAsync}
              <View {fitRequested} {presetRequested} />
            {:else}
              <div class="stage-loading">Loading 3D view…</div>
            {/if}
          </div>
        {/snippet}
      </SplitPane>
    {:else}
      <div class="stage">render area ({tab})</div>
    {/if}
  </Shell>
{:else}
  <main class="empty"><DropZone /></main>
{/if}

<SearchBar open={searchOpen} onClose={() => (searchOpen = false)} />

<HelpOverlay open={helpOpen} onClose={() => (helpOpen = false)} />

<Toast />

<style>
  .empty { padding: 3rem; min-height: 100dvh; display: grid; place-items: center; background: var(--kv-bg); }
  .panel, .stage { padding: 1rem; color: var(--kv-text-dim); }
  .stage { color: var(--kv-text); }
  .pane-with-picker {
    height: 100%;
    display: grid;
    grid-template-rows: auto 1fr;
  }
  .pane-with-picker select {
    padding: 4px 8px; border: none;
    border-bottom: 1px solid var(--kv-border);
    background: var(--kv-surface-2); color: var(--kv-text);
    font-size: 0.75rem;
  }
  .pane-with-picker > :global(:nth-child(2)) {
    min-height: 0;
  }
  .pcb-sidebar { display: grid; grid-template-rows: auto 1fr; min-height: 0; height: 100%; }
  .pcb-sidebar > :global(*:nth-child(1)) { border-bottom: 1px solid var(--kv-border); }
  .pcb-sidebar > :global(*:nth-child(2)) { min-height: 0; }
  .stage-loading {
    display: grid; place-items: center;
    width: 100%; height: 100%;
    background: var(--kv-render-bg);
    color: var(--kv-text-dim);
    font-size: 0.9rem;
  }
</style>
