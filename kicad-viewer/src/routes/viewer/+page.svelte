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
  import LeftSidebar from '$lib/ui/LeftSidebar.svelte';
  import SearchBar from '$lib/ui/SearchBar.svelte';
  import SplitPane from '$lib/ui/SplitPane.svelte';
  import { project, componentsByUuid, setProjectRevokingGlb } from '$lib/stores/project';
  import { selection } from '$lib/stores/selection';
  import { leftSidebarTab } from '$lib/stores/leftSidebar';
  import { model3dStatus, acknowledgeReady } from '$lib/stores/model3d';
  import { loadRecent, clearRecent } from '$lib/stores/recent';
  import { classifyFiles, rootSchematic } from '$lib/loader/blob';
  import { toProject } from '$lib/adapter/adapter';

  let tab = $state('sch');
  let searchOpen = $state(false);
  let helpOpen = $state(false);
  let fitRequested = $state(0);
  let panPulse = $state({ dx: 0, dy: 0, seq: 0 });
  let zoomPulse = $state({ factor: 1, seq: 0 });
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

  // Keep the schematic's active sheet in sync with the selected component, no
  // matter where the selection came from (search / PCB / components panel).
  // That way, when the user navigates to the Schematic tab they land on the
  // right page with the part already centered. Only the search bar yanks the
  // top-level tab across — PCB clicks leave you where you were.
  $effect(() => {
    const s = $selection;
    if (!s || s.kind !== 'component') return;
    if (s.source === 'sch') return;
    const c = $componentsByUuid.get(s.uuid);
    if (!c) return;
    if (activeSheet !== c.sheetUuid) activeSheet = c.sheetUuid;
    if (s.source === 'search' && tab !== 'sch' && tab !== 'split') tab = 'sch';
    if (s.source === 'panel' && tab !== 'sch' && tab !== 'split' && tab !== '3d') tab = 'sch';
  });

  onMount(() => {
    const teardown = installKeyboardShortcuts({
      setTab: (t) => (tab = t),
      onSearch: () => (searchOpen = true),
      onFit: () => fitRequested++,
      onPan: (dx, dy) => { panPulse = { dx, dy, seq: panPulse.seq + 1 }; },
      onZoom: (factor) => { zoomPulse = { factor, seq: zoomPulse.seq + 1 }; },
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
        leftSidebarTab.set(0);
        queueMicrotask(() => {
          const panel = document.getElementById('layer-panel');
          panel?.querySelector<HTMLInputElement>('input[type="checkbox"]')?.focus();
        });
      },
      onPreset: (preset) => {
        const threeDIsActive = tab === '3d' ||
          (tab === 'split' && (leftPane === '3d' || rightPane === '3d'));
        if (!threeDIsActive) return;
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
    if (blob.step) {
      const u8 = blob.files[blob.step] as Uint8Array;
      p.stepUrl = URL.createObjectURL(new Blob([u8 as BlobPart], { type: 'model/step' }));
    } else if (blob.glb) {
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
      {#if tab === 'sch' || tab === 'pcb' || tab === '3d'}
        <LeftSidebar
          view={tab as 'sch' | 'pcb' | '3d'}
          activeSheet={activeSheet}
          onSelectSheet={(u) => (activeSheet = u)}
        />
      {:else}
        <div class="panel">({tab} sidebar)</div>
      {/if}
    {/snippet}
    {#snippet inspector()}<Inspector />{/snippet}
    {#if tab === 'sch'}
      <SchematicView activeSheetUuid={activeSheet} onNavigateSheet={(u) => (activeSheet = u)} {fitRequested} {panPulse} {zoomPulse} />
    {:else if tab === 'pcb'}
      <PcbView onCursor={(c) => (cursorMm = c)} {fitRequested} {panPulse} {zoomPulse} />
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
              <SchematicView activeSheetUuid={activeSheet} onNavigateSheet={(u) => (activeSheet = u)} {fitRequested} {panPulse} {zoomPulse} />
            {:else if leftPane === 'pcb'}
              <PcbView onCursor={(c) => (cursorMm = c)} {fitRequested} {panPulse} {zoomPulse} />
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
              <SchematicView activeSheetUuid={activeSheet} onNavigateSheet={(u) => (activeSheet = u)} {fitRequested} {panPulse} {zoomPulse} />
            {:else if rightPane === 'pcb'}
              <PcbView onCursor={(c) => (cursorMm = c)} {fitRequested} {panPulse} {zoomPulse} />
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

<!-- Corner notification when a 3D model finishes loading while the user is
     on a different tab. Acknowledged on click (→ switches to 3D) or dismiss. -->
{#if $model3dStatus.kind === 'ready' && !$model3dStatus.acknowledged && tab !== '3d'}
  <div class="model3d-pill" role="status">
    <button
      class="go"
      onclick={() => { tab = '3d'; acknowledgeReady(); }}
    >3D model ready →</button>
    <button
      class="dismiss"
      onclick={() => acknowledgeReady()}
      aria-label="Dismiss"
    >×</button>
  </div>
{/if}

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
  .stage-loading {
    display: grid; place-items: center;
    width: 100%; height: 100%;
    background: var(--kv-render-bg);
    color: var(--kv-text-dim);
    font-size: 0.9rem;
  }
  .model3d-pill {
    position: fixed; right: 18px; bottom: 18px;
    display: flex; align-items: center; gap: 2px;
    background: var(--kv-surface); color: var(--kv-text);
    border: 1px solid var(--kv-accent, #6aa6ff);
    border-radius: 20px; padding: 2px 2px 2px 10px;
    font-size: 0.8rem;
    box-shadow: 0 6px 22px rgba(0, 0, 0, 0.35);
    z-index: 50;
  }
  .model3d-pill .go {
    background: transparent; border: none; color: var(--kv-accent, #6aa6ff);
    cursor: pointer; padding: 6px 10px; font-weight: 600; font-size: 0.8rem;
  }
  .model3d-pill .dismiss {
    background: transparent; border: none; color: var(--kv-text-dim);
    cursor: pointer; padding: 6px 8px;
    font-size: 1rem; line-height: 1;
  }
  .model3d-pill .dismiss:hover { color: var(--kv-text); }
</style>
