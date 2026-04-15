<script lang="ts">
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';
  import { installKeyboardShortcuts } from '$lib/keys';
  import Shell from '$lib/ui/Shell.svelte';
  import DropZone from '$lib/ui/DropZone.svelte';
  import Toast from '$lib/ui/Toast.svelte';
  import Inspector from '$lib/ui/Inspector.svelte';
  import SchematicView from '$lib/views/SchematicView.svelte';
  import SheetTree from '$lib/ui/SheetTree.svelte';
  import SearchBar from '$lib/ui/SearchBar.svelte';
  import { project } from '$lib/stores/project';

  let tab = $state('sch');
  let searchOpen = $state(false);
  let fitRequested = $state(0);
  let activeSheet = $state<string | null>(null);

  $effect(() => {
    if (!activeSheet && $project) activeSheet = $project.sheets[0]?.uuid ?? null;
  });

  onMount(() =>
    installKeyboardShortcuts({
      setTab: (t) => (tab = t),
      onSearch: () => (searchOpen = true),
      onFit: () => fitRequested++,
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
      onFocusLayers: () => { /* wired in Task 25 */ }
    })
  );
</script>

<svelte:head><title>Viewer — kicad-viewer</title></svelte:head>

{#if $project}
  <Shell {tab} onTabChange={(v) => (tab = v)}>
    {#snippet sidebar()}
      {#if tab === 'sch'}
        <SheetTree activeUuid={activeSheet} onSelect={(u) => (activeSheet = u)} />
      {:else}
        <div class="panel">({tab} sidebar)</div>
      {/if}
    {/snippet}
    {#snippet inspector()}<Inspector />{/snippet}
    {#if tab === 'sch'}
      <SchematicView activeSheetUuid={activeSheet} onNavigateSheet={(u) => (activeSheet = u)} />
    {:else}
      <div class="stage">render area ({tab})</div>
    {/if}
  </Shell>
{:else}
  <main class="empty"><DropZone /></main>
{/if}

<SearchBar open={searchOpen} onClose={() => (searchOpen = false)} />

<Toast />

<style>
  .empty { padding: 3rem; min-height: 100dvh; display: grid; place-items: center; background: var(--kv-bg); }
  .panel, .stage { padding: 1rem; color: var(--kv-text-dim); }
  .stage { color: var(--kv-text); }
</style>
